"""CPV Version 2008 lookup and descendant expansion."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET

import httpx
from sqlalchemy import text

from db import SCHEMA
from pricing.identifiers import cpv_prefix

VERSION = "2008"
CONCEPT_URI = "http://data.europa.eu/cpv/cpv/{code}"
RESOURCE_URI = "https://publications.europa.eu/resource/authority/cpv/cpv/{code}"
_NS = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "owl": "http://www.w3.org/2002/07/owl#",
}


def expand_cpv(db, code: str, *, limit: int = 500) -> list[dict]:
    """Return the selected CPV concept and imported descendants."""
    clean = "".join(c for c in code if c.isdigit())[:8]
    prefix = cpv_prefix(clean)
    rows = db.execute(text(f"""
        SELECT code, check_digit, parent_code, level, label_en, labels
        FROM {SCHEMA}.cpv_codes
        WHERE version = :version AND code LIKE :prefix
        ORDER BY level, code
        LIMIT :limit
    """), {"version": VERSION, "prefix": f"{prefix}%", "limit": limit}).fetchall()
    return [dict(r._mapping) for r in rows]


def search_cpv(db, query: str, *, lang: str = "en", limit: int = 20) -> list[dict]:
    clean = (query or "").strip()
    if clean.replace("-", "").isdigit():
        return expand_cpv(db, clean, limit=limit)
    rows = db.execute(text(f"""
        SELECT code, check_digit, parent_code, level, label_en, labels
        FROM {SCHEMA}.cpv_codes
        WHERE label_en ILIKE :query OR COALESCE(labels ->> :lang, '') ILIKE :query
        ORDER BY CASE WHEN label_en ILIKE :starts THEN 0 ELSE 1 END, level, code
        LIMIT :limit
    """), {"query": f"%{clean}%", "starts": f"{clean}%", "lang": lang, "limit": limit}).fetchall()
    return [dict(r._mapping) for r in rows]


def concept_uri(code: str) -> str:
    return CONCEPT_URI.format(code="".join(c for c in code if c.isdigit())[:8])


def fetch_official_concept(code: str, *, timeout: float = 15.0) -> dict:
    """Fetch one concept directly from the EU Publications Office SKOS service."""
    clean = "".join(c for c in code if c.isdigit())[:8]
    response = httpx.get(
        RESOURCE_URI.format(code=clean),
        headers={"Accept": "application/rdf+xml", "User-Agent": "FastCPI/1.0 (+https://cpi.fastsme.com)"},
        follow_redirects=True,
        timeout=timeout,
    )
    response.raise_for_status()
    root = ET.fromstring(response.content)
    about_key = f"{{{_NS['rdf']}}}about"
    resource_key = f"{{{_NS['rdf']}}}resource"
    target = concept_uri(clean)
    node = next((n for n in root.findall("rdf:Description", _NS) if n.attrib.get(about_key) == target), None)
    if node is None:
        raise ValueError(f"CPV concept {clean} was not returned by the official vocabulary")
    labels = {n.attrib.get("{http://www.w3.org/XML/1998/namespace}lang", "en"): (n.text or "").strip()
              for n in node.findall("skos:prefLabel", _NS)}
    broader = node.find("skos:broader", _NS)
    children = []
    for child in node.findall("skos:narrower", _NS):
        match = re.search(r"/(\d{8})$", child.attrib.get(resource_key, ""))
        if match:
            children.append(match.group(1))
    parent_match = re.search(r"/(\d{8})$", broader.attrib.get(resource_key, "")) if broader is not None else None
    version = node.findtext("owl:versionInfo", VERSION, _NS)
    return {
        "code": clean,
        "version": version,
        "parent_code": parent_match.group(1) if parent_match else None,
        "label_en": labels.get("en") or next(iter(labels.values()), clean),
        "labels": labels,
        "children": sorted(set(children)),
        "concept_uri": target,
    }


def import_official_tree(db, code: str, *, max_nodes: int = 500) -> list[dict]:
    """Recursively cache a CPV branch and return all imported concepts.

    The cap prevents an accidental request for the whole vocabulary from
    monopolising a web request; scheduled imports can use a higher value.
    """
    queue = ["".join(c for c in code if c.isdigit())[:8]]
    imported: list[dict] = []
    seen: set[str] = set()
    while queue and len(imported) < max_nodes:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        concept = fetch_official_concept(current)
        level = len(cpv_prefix(current))
        db.execute(text(f"""
            INSERT INTO {SCHEMA}.cpv_codes
                (code, check_digit, version, parent_code, level, label_en, labels, concept_uri)
            VALUES (:code, NULL, :version, :parent_code, :level, :label_en, CAST(:labels AS jsonb), :concept_uri)
            ON CONFLICT (code, version) DO UPDATE SET
                parent_code = EXCLUDED.parent_code,
                level = EXCLUDED.level,
                label_en = EXCLUDED.label_en,
                labels = EXCLUDED.labels,
                concept_uri = EXCLUDED.concept_uri,
                is_active = TRUE
        """), {**concept, "level": level, "labels": json.dumps(concept["labels"])})
        imported.append(concept)
        queue.extend(concept["children"])
    db.commit()
    return imported
