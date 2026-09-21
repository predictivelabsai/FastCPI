"""Municipal catalogue loading and validation."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile


CATALOG_VERSION = "eu-local-government-v1-2026-09-21"
CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "municipal_catalog.tsv"
MONITORING_TIERS = {"web_price", "quote_based", "tender_benchmark"}
ITEM_TYPES = {"good", "service"}


def load_municipal_catalog(path: Path = CATALOG_PATH) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = [dict(row) for row in csv.DictReader(stream, delimiter="\t")]
    validate_municipal_catalog(rows)
    return rows


def validate_municipal_catalog(rows: list[dict[str, str]]) -> None:
    if len(rows) < 100:
        raise ValueError("municipal catalogue must contain at least 100 entries")
    names = [row.get("name", "").strip().casefold() for row in rows]
    codes = [row.get("cpv_code", "").strip() for row in rows]
    duplicates = [name for name, count in Counter(names).items() if name and count > 1]
    if duplicates:
        raise ValueError("duplicate catalogue names: " + ", ".join(sorted(duplicates)))
    if len(set(codes)) != len(codes):
        raise ValueError("each seeded catalogue entry must use a distinct CPV code")
    for position, row in enumerate(rows, start=2):
        if not row.get("name", "").strip() or not row.get("name_fr", "").strip():
            raise ValueError(f"row {position}: English and French names are required")
        if row.get("item_type") not in ITEM_TYPES:
            raise ValueError(f"row {position}: unsupported item_type")
        if len(row.get("cpv_code", "")) != 8 or not row["cpv_code"].isdigit():
            raise ValueError(f"row {position}: CPV code must contain eight digits")
        if (not row.get("cpv_label", "").strip()
                or not row.get("cpv_label_fr", "").strip()
                or not row.get("canonical_unit", "").strip()):
            raise ValueError(f"row {position}: English/French CPV labels and canonical unit are required")
        if row.get("monitoring_tier") not in MONITORING_TIERS:
            raise ValueError(f"row {position}: unsupported monitoring tier")
        if bool(row.get("identifier_type")) != bool(row.get("identifier_value")):
            raise ValueError(f"row {position}: identifier type and value must be provided together")


def catalogue_summary(rows: list[dict[str, str]]) -> dict:
    return {
        "version": CATALOG_VERSION,
        "entries": len(rows),
        "goods": sum(row["item_type"] == "good" for row in rows),
        "services": sum(row["item_type"] == "service" for row in rows),
        "sectors": dict(sorted(Counter(row["sector"] for row in rows).items())),
        "monitoring_tiers": dict(sorted(Counter(row["monitoring_tier"] for row in rows).items())),
    }


def validate_against_official_cpv(rows: list[dict[str, str]], ods_path: Path) -> None:
    """Validate codes plus English/French labels against the official CPV 2008 ODS asset."""
    namespaces = {
        "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
        "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    }
    with ZipFile(ods_path) as archive:
        root = ET.fromstring(archive.read("content.xml"))
    table = root.findall(".//table:table", namespaces)[0]
    official: dict[str, tuple[str, str]] = {}
    for xml_row in table.findall("table:table-row", namespaces)[1:]:
        values = [
            " ".join("".join(node.itertext()) for node in cell.findall(".//text:p", namespaces)).strip()
            for cell in xml_row.findall("table:table-cell", namespaces)
        ]
        if len(values) > 10 and values[0]:
            official[values[0].split("-", 1)[0]] = (values[6], values[10])
    mismatches = []
    for row in rows:
        expected = official.get(row["cpv_code"])
        actual = (row["cpv_label"], row["cpv_label_fr"])
        if expected != actual:
            mismatches.append(f"{row['cpv_code']}: expected {expected!r}, got {actual!r}")
    if mismatches:
        raise ValueError("official CPV validation failed: " + "; ".join(mismatches))
