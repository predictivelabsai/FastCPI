"""Car Deals Scanner -- finds fresh daily deals from the latest scrape run.

Freshness is relative to the most recent scrape, not wall-clock time.
This ensures stats and sections always reflect real data even if the
last scrape was days ago.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from urllib.parse import quote

log = logging.getLogger(__name__)

BASE_URL = os.getenv("SERVICE_URL_CARHERO", "https://carhero.chat")

COUNTRY_LABELS = {
    "GB": "UK", "DE": "Germany", "EU": "Other EU",
    "EE": "Estonia", "LT": "Lithuania", "LV": "Latvia", "SE": "Sweden",
    "PL": "Poland", "ES": "Spain", "NL": "Netherlands", "FI": "Finland",
    "DK": "Denmark", "IE": "Ireland", "NO": "Norway", "PT": "Portugal",
    "RO": "Romania",
}
PROVIDER_LABELS = {
    "autotrader": "AutoTrader",
    "mobile_de": "mobile.de",
    "autoscout24": "AutoScout24",
    "autohero": "Autohero",
    "theparking": "TheParking",
    "auto24_ee": "Auto24.ee",
    "auto24_lt": "Auto24.lt",
    "auto24_lv": "Auto24.lv",
    "blocket": "Blocket.se",
    "otomoto": "Otomoto.pl",
    "coches": "Coches.net",
    "marktplaats": "Marktplaats.nl",
    "nettiauto": "Nettiauto.com",
    "bilbasen": "Bilbasen.dk",
    "donedeal": "DoneDeal.ie",
    "finn": "Finn.no",
    "standvirtual": "Standvirtual.com",
    "autovit": "Autovit.ro",
    "collectingcars": "Collecting Cars",
}


def _scrape_cutoff(db) -> str:
    """Compute the cutoff timestamp for 'latest scrape run'.

    Returns a SQL expression string. The cutoff is MAX(scraped_at) minus
    a 4-hour buffer to cover the span of a single scrape run across all
    providers.  This means stats always reflect the most recent run,
    even if it happened days ago.
    """
    from sqlalchemy import text
    row = db.execute(text(
        "SELECT MAX(scraped_at) FROM carhero.car_listings WHERE status = 'active'"
    )).scalar()
    if not row:
        return "NOW() - INTERVAL '1 day'"
    return f"TIMESTAMP '{row}' - INTERVAL '4 hours'"


def scan_price_comparisons(limit: int = 25) -> list[dict]:
    """Price arbitrage grouped by make/model/year.

    For each make+model+year combo that appears in 2+ sources, returns the
    cheapest and most expensive listing with source details, sorted by
    savings percentage.  This is the core of the Daily Scan.
    """
    from db import SessionLocal
    from sqlalchemy import text

    db = SessionLocal()
    try:
        cutoff = _scrape_cutoff(db)
        sql = text(f"""
            WITH fresh AS (
                SELECT id, make, model, year, price_eur, mileage_km,
                       country, provider, source_url, fuel_type, variant
                FROM carhero.car_listings
                WHERE status = 'active' AND price_eur > 500
                  AND year IS NOT NULL
                  AND canonical_variant IS NULL
                  AND scraped_at > ({cutoff})
            ),
            medians AS (
                SELECT make, model, year,
                       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_eur) AS median_price
                FROM fresh
                GROUP BY make, model, year
            ),
            cleaned AS (
                SELECT f.*
                FROM fresh f
                JOIN medians m USING (make, model, year)
                WHERE f.price_eur < m.median_price * 5
                  AND f.price_eur > m.median_price * 0.2
            ),
            grouped AS (
                SELECT c.make, c.model, c.year,
                       COUNT(*) AS listing_count,
                       COUNT(DISTINCT c.country || '/' || c.provider) AS source_count,
                       ROUND(MIN(c.price_eur)::numeric, 0) AS min_price,
                       ROUND(MAX(c.price_eur)::numeric, 0) AS max_price,
                       ROUND(AVG(c.price_eur)::numeric, 0) AS avg_price,
                       ROUND(m.median_price::numeric, 0) AS median_price,
                       (MAX(c.price_eur) - MIN(c.price_eur)) AS savings_eur,
                       ROUND(((MAX(c.price_eur) - MIN(c.price_eur))
                              / NULLIF(AVG(c.price_eur), 0) * 100)::numeric, 1) AS savings_pct
                FROM cleaned c
                JOIN medians m USING (make, model, year)
                GROUP BY c.make, c.model, c.year, m.median_price
                HAVING COUNT(*) >= 2
                   AND COUNT(DISTINCT c.country || '/' || c.provider) >= 2
                   AND (MAX(c.price_eur) - MIN(c.price_eur)) > 500
            )
            SELECT * FROM grouped
            WHERE savings_pct BETWEEN 5 AND 300
            ORDER BY savings_eur DESC
            LIMIT :lim
        """)
        rows = [dict(r._mapping) for r in db.execute(sql, {"lim": limit})]

        for row in rows:
            med = float(row["median_price"])
            c = db.execute(text(f"""
                SELECT id, price_eur, country, provider, source_url, mileage_km, variant, fuel_type
                FROM carhero.car_listings
                WHERE make = :make AND model = :model AND year = :year
                  AND status = 'active' AND price_eur > 500
                  AND canonical_variant IS NULL
                  AND price_eur BETWEEN :lo AND :hi
                  AND scraped_at > ({cutoff})
                ORDER BY price_eur ASC LIMIT 1
            """), {"make": row["make"], "model": row["model"], "year": row["year"],
                   "lo": med * 0.2, "hi": med * 5}).first()
            if c:
                row["cheap_price"] = float(c.price_eur)
                row["cheap_country"] = c.country
                row["cheap_provider"] = c.provider
                row["cheap_url"] = c.source_url
                row["cheap_km"] = c.mileage_km
                row["cheap_variant"] = c.variant
                row["cheap_fuel"] = c.fuel_type

            p = db.execute(text(f"""
                SELECT id, price_eur, country, provider, source_url, mileage_km, variant, fuel_type
                FROM carhero.car_listings
                WHERE make = :make AND model = :model AND year = :year
                  AND status = 'active' AND price_eur > 500
                  AND canonical_variant IS NULL
                  AND price_eur BETWEEN :lo AND :hi
                  AND scraped_at > ({cutoff})
                ORDER BY price_eur DESC LIMIT 1
            """), {"make": row["make"], "model": row["model"], "year": row["year"],
                   "lo": med * 0.2, "hi": med * 5}).first()
            if p:
                row["expensive_price"] = float(p.price_eur)
                row["expensive_country"] = p.country
                row["expensive_provider"] = p.provider
                row["expensive_url"] = p.source_url
                row["expensive_km"] = p.mileage_km
                row["expensive_variant"] = p.variant
                row["expensive_fuel"] = p.fuel_type

        return rows
    finally:
        db.close()


def scan_variant_comparisons(limit: int = 25) -> list[dict]:
    """Price arbitrage grouped by canonical_variant (verified variant matches).

    Groups listings that matched a curated variant catalog entry, so the
    comparison is apples-to-apples (e.g., "Porsche 911 GT3 (991)" only).
    Includes median-based outlier protection.
    """
    from db import SessionLocal
    from sqlalchemy import text

    db = SessionLocal()
    try:
        cutoff = _scrape_cutoff(db)
        sql = text(f"""
            WITH fresh AS (
                SELECT id, make, model, variant, year, price_eur, mileage_km,
                       country, provider, source_url, fuel_type, canonical_variant
                FROM carhero.car_listings
                WHERE status = 'active' AND price_eur > 500
                  AND canonical_variant IS NOT NULL
                  AND scraped_at > ({cutoff})
            ),
            medians AS (
                SELECT canonical_variant,
                       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_eur) AS median_price
                FROM fresh
                GROUP BY canonical_variant
            ),
            cleaned AS (
                SELECT f.*
                FROM fresh f
                JOIN medians m USING (canonical_variant)
                WHERE f.price_eur < m.median_price * 5
                  AND f.price_eur > m.median_price * 0.2
            ),
            grouped AS (
                SELECT c.canonical_variant,
                       MIN(c.make) AS make,
                       COUNT(*) AS listing_count,
                       COUNT(DISTINCT c.provider) AS source_count,
                       ROUND(MIN(c.price_eur)::numeric, 0) AS min_price,
                       ROUND(MAX(c.price_eur)::numeric, 0) AS max_price,
                       ROUND(AVG(c.price_eur)::numeric, 0) AS avg_price,
                       ROUND(m.median_price::numeric, 0) AS median_price,
                       (MAX(c.price_eur) - MIN(c.price_eur)) AS savings_eur,
                       ROUND(((MAX(c.price_eur) - MIN(c.price_eur))
                              / NULLIF(AVG(c.price_eur), 0) * 100)::numeric, 1) AS savings_pct
                FROM cleaned c
                JOIN medians m USING (canonical_variant)
                GROUP BY c.canonical_variant, m.median_price
                HAVING COUNT(*) >= 2
                   AND (MAX(c.price_eur) - MIN(c.price_eur)) > 500
            )
            SELECT * FROM grouped
            WHERE savings_pct BETWEEN 3 AND 300
            ORDER BY savings_eur DESC
            LIMIT :lim
        """)
        rows = [dict(r._mapping) for r in db.execute(sql, {"lim": limit})]

        for row in rows:
            cv = row["canonical_variant"]
            med = float(row["median_price"])
            c = db.execute(text(f"""
                SELECT id, price_eur, country, provider, source_url, mileage_km, variant, fuel_type, year
                FROM carhero.car_listings
                WHERE canonical_variant = :cv AND status = 'active' AND price_eur > 500
                  AND price_eur BETWEEN :lo AND :hi
                  AND scraped_at > ({cutoff})
                ORDER BY price_eur ASC LIMIT 1
            """), {"cv": cv, "lo": med * 0.2, "hi": med * 5}).first()
            if c:
                row["cheap_price"] = float(c.price_eur)
                row["cheap_country"] = c.country
                row["cheap_provider"] = c.provider
                row["cheap_url"] = c.source_url
                row["cheap_km"] = c.mileage_km
                row["cheap_variant"] = c.variant
                row["cheap_fuel"] = c.fuel_type
                row["cheap_year"] = c.year

            p = db.execute(text(f"""
                SELECT id, price_eur, country, provider, source_url, mileage_km, variant, fuel_type, year
                FROM carhero.car_listings
                WHERE canonical_variant = :cv AND status = 'active' AND price_eur > 500
                  AND price_eur BETWEEN :lo AND :hi
                  AND scraped_at > ({cutoff})
                ORDER BY price_eur DESC LIMIT 1
            """), {"cv": cv, "lo": med * 0.2, "hi": med * 5}).first()
            if p:
                row["expensive_price"] = float(p.price_eur)
                row["expensive_country"] = p.country
                row["expensive_provider"] = p.provider
                row["expensive_url"] = p.source_url
                row["expensive_km"] = p.mileage_km
                row["expensive_variant"] = p.variant
                row["expensive_fuel"] = p.fuel_type
                row["expensive_year"] = p.year

        return rows
    finally:
        db.close()


def scan_price_drops(limit: int = 10) -> list[dict]:
    """Listings whose price dropped in the latest scrape vs their previous price."""
    from db import SessionLocal
    from sqlalchemy import text

    db = SessionLocal()
    try:
        cutoff = _scrape_cutoff(db)
        sql = text(f"""
            SELECT l.make, l.model, l.variant, l.year, l.mileage_km,
                   l.price_eur, l.country, l.provider, l.fuel_type,
                   l.transmission, l.source_url,
                   ph.price_eur AS old_price,
                   (ph.price_eur - l.price_eur) AS drop_eur,
                   ROUND(((ph.price_eur - l.price_eur) / ph.price_eur * 100)::numeric, 1) AS drop_pct
            FROM carhero.car_listings l
            JOIN carhero.price_history ph ON ph.listing_id = l.id
            WHERE l.status = 'active' AND l.price_eur > 0
              AND ph.recorded_at > ({cutoff})
              AND ph.price_eur > l.price_eur
            ORDER BY (ph.price_eur - l.price_eur)::float / ph.price_eur DESC
            LIMIT :lim
        """)
        return [dict(r._mapping) for r in db.execute(sql, {"lim": limit})]
    finally:
        db.close()


def scan_freshness_stats() -> dict:
    """Summary stats for the digest header, based on latest scrape run."""
    from db import SessionLocal
    from sqlalchemy import text

    db = SessionLocal()
    try:
        cutoff = _scrape_cutoff(db)
        row = db.execute(text(f"""
            SELECT
                COUNT(*) AS total_active,
                COUNT(*) FILTER (
                    WHERE scraped_at > ({cutoff})
                ) AS fresh_count,
                COUNT(*) FILTER (
                    WHERE created_at > ({cutoff})
                ) AS new_count,
                COUNT(DISTINCT provider) FILTER (
                    WHERE scraped_at > ({cutoff})
                ) AS providers_scraped,
                COUNT(DISTINCT country) FILTER (
                    WHERE scraped_at > ({cutoff})
                ) AS countries_covered,
                MAX(scraped_at) AS last_scrape
            FROM carhero.car_listings
            WHERE status = 'active'
        """)).first()
        return dict(row._mapping) if row else {}
    finally:
        db.close()


# ── Formatting helpers ────────────────────────────────────────────────


def _fmt_eur(n) -> str:
    if not n:
        return "--"
    try:
        return f"€{float(n):,.0f}"
    except (TypeError, ValueError):
        return str(n)


def _source_label(country: str | None, provider: str | None) -> str:
    c = COUNTRY_LABELS.get(country or "", country or "")
    p = PROVIDER_LABELS.get(provider or "", provider or "")
    return f"{c} / {p}"


# ── HTML builder ──────────────────────────────────────────────────────


def build_digest_html(
    comparisons: list[dict],
    price_drops: list[dict] | None = None,
    stats: dict | None = None,
    variant_comparisons: list[dict] | None = None,
) -> str:
    now = datetime.now()
    today = now.strftime("%A, %B %d, %Y")

    stats = stats or {}
    fresh = stats.get("fresh_count", 0)
    new = stats.get("new_count", 0)
    providers = stats.get("providers_scraped", 0)
    countries = stats.get("countries_covered", 0)

    link_style = "color:inherit; text-decoration:none;"

    # --- Stats banner ---
    stats_html = ""
    if fresh > 0:
        stats_html = f"""
    <div style="background:#F0FDF4; border:1px solid #BBF7D0; border-radius:8px; padding:12px 16px; margin-bottom:20px; text-align:center;">
        <span style="font-size:13px; color:#15803D;">
            <strong>{fresh:,}</strong> listings refreshed &middot;
            <strong>{new:,}</strong> new today &middot;
            <strong>{providers}</strong> providers &middot;
            <strong>{countries}</strong> countries
        </span>
    </div>"""

    # --- Price drops section ---
    drops_html = ""
    if price_drops:
        drop_cards = ""
        for d in price_drops:
            km = f"{int(d['mileage_km']):,} km" if d.get("mileage_km") else ""
            src = _source_label(d.get("country"), d.get("provider"))
            deal_url = f"{BASE_URL}/app?deal={quote(d['make'] + ' ' + d['model'])}"
            drop_pct = float(d.get("drop_pct") or 0)
            specs = " &middot; ".join(filter(None, [str(d.get("year") or ""), km, d.get("variant") or ""]))
            drop_cards += f"""
            <div style="border:1px solid #E5E7EB; border-radius:8px; padding:12px; margin-bottom:8px;">
                <div style="display:flex; justify-content:space-between; align-items:baseline;">
                    <a href="{deal_url}" style="color:#1A1A1A; text-decoration:none; font-weight:600; font-size:14px;">{d['make']} {d['model']}</a>
                    <span style="background:#16A34A; color:white; padding:2px 8px; border-radius:12px; font-size:12px; font-weight:600;">&darr;{drop_pct:.0f}%</span>
                </div>
                <div style="font-size:12px; color:#6B7280; margin-top:2px;">{specs} &middot; {src}</div>
                <div style="margin-top:6px;">
                    <span style="font-size:15px; font-weight:700; color:#16A34A;">{_fmt_eur(d.get('price_eur'))}</span>
                    <span style="text-decoration:line-through; color:#9CA3AF; font-size:12px; margin-left:6px;">{_fmt_eur(d.get('old_price'))}</span>
                </div>
            </div>"""

        drops_html = f"""
    <div style="background:#FFFFFF; border:1px solid #E5E7EB; border-radius:8px; padding:16px; margin-bottom:20px;">
        <h2 style="color:#1A1A1A; font-size:16px; font-weight:600; margin:0 0 4px;">Price Drops</h2>
        <p style="color:#6B7280; font-size:12px; margin:0 0 12px;">
            Prices reduced since last scrape.
        </p>
        {drop_cards}
    </div>"""

    # --- Variant comparisons section ---
    variant_html = ""
    if variant_comparisons:
        vcards = ""
        for d in variant_comparisons:
            savings_pct = float(d.get("savings_pct") or 0)
            savings_eur = float(d.get("savings_eur") or 0)
            badge_color = "#16A34A" if savings_pct >= 15 else "#F59E0B" if savings_pct >= 8 else "#6B7280"
            cheap_src = _source_label(d.get("cheap_country"), d.get("cheap_provider"))
            expensive_src = _source_label(d.get("expensive_country"), d.get("expensive_provider"))
            cheap_url = d.get("cheap_url") or ""
            expensive_url = d.get("expensive_url") or ""
            cheap_link = f'<a href="{cheap_url}" style="font-size:11px; color:#15803D; text-decoration:underline;">View listing</a>' if cheap_url else ""
            expensive_link = f'<a href="{expensive_url}" style="font-size:11px; color:#991B1B; text-decoration:underline;">View listing</a>' if expensive_url else ""
            cheap_km = f"{int(d['cheap_km']):,} km" if d.get("cheap_km") else ""
            exp_km = f"{int(d['expensive_km']):,} km" if d.get("expensive_km") else ""
            cheap_yr = str(d['cheap_year']) if d.get("cheap_year") else ""
            exp_yr = str(d['expensive_year']) if d.get("expensive_year") else ""
            cheap_meta = " &middot; ".join(filter(None, [cheap_src, cheap_yr, cheap_km]))
            exp_meta = " &middot; ".join(filter(None, [expensive_src, exp_yr, exp_km]))

            vcards += f"""
            <div style="border:1px solid #DBEAFE; border-radius:8px; padding:12px; margin-bottom:8px;">
                <div style="display:flex; justify-content:space-between; align-items:baseline; flex-wrap:wrap; gap:4px;">
                    <div>
                        <strong style="font-size:14px; color:#1A1A1A;">{d['canonical_variant']}</strong>
                        <span style="display:inline-block; background:#EFF6FF; color:#1D4ED8; font-size:10px; font-weight:600; padding:1px 6px; border-radius:8px; margin-left:4px;">Verified</span>
                        <br><span style="font-size:11px; color:#9CA3AF;">{int(d.get('listing_count') or 0)} listings &middot; {int(d.get('source_count') or 0)} sources &middot; median {_fmt_eur(d.get('median_price'))}</span>
                    </div>
                    <span style="background:{badge_color}; color:white; padding:2px 8px; border-radius:12px; font-size:12px; font-weight:600; white-space:nowrap;">
                        Save {_fmt_eur(savings_eur)} ({savings_pct:.0f}%)
                    </span>
                </div>
                <!--[if mso]><table width="100%"><tr><td width="48%" valign="top"><![endif]-->
                <div style="display:inline-block; width:48%; vertical-align:top; min-width:120px; background:#F0FDF4; border-radius:6px; padding:8px; margin-top:8px; box-sizing:border-box;">
                    <div style="font-size:10px; color:#16A34A; font-weight:600; text-transform:uppercase;">Cheapest</div>
                    <div style="font-size:15px; font-weight:700; color:#15803D;">{_fmt_eur(d.get('cheap_price'))}</div>
                    <div style="font-size:11px; color:#6B7280;">{cheap_meta}</div>
                    {cheap_link}
                </div>
                <!--[if mso]></td><td width="4%"></td><td width="48%" valign="top"><![endif]-->
                <div style="display:inline-block; width:48%; vertical-align:top; min-width:120px; background:#FEF2F2; border-radius:6px; padding:8px; margin-top:8px; box-sizing:border-box;">
                    <div style="font-size:10px; color:#DC2626; font-weight:600; text-transform:uppercase;">Most Expensive</div>
                    <div style="font-size:15px; font-weight:700; color:#991B1B;">{_fmt_eur(d.get('expensive_price'))}</div>
                    <div style="font-size:11px; color:#6B7280;">{exp_meta}</div>
                    {expensive_link}
                </div>
                <!--[if mso]></td></tr></table><![endif]-->
            </div>"""

        variant_html = f"""
    <div style="background:#FFFFFF; border:1px solid #DBEAFE; border-radius:8px; padding:16px; margin-bottom:20px;">
        <h2 style="color:#1A1A1A; font-size:16px; font-weight:600; margin:0 0 4px;">Verified Variant Deals</h2>
        <p style="color:#6B7280; font-size:12px; margin:0 0 12px;">
            Apples-to-apples comparisons for specific car variants across markets.
        </p>
        {vcards}
    </div>"""

    # --- Price comparisons section ---
    deal_cards = ""
    for d in comparisons:
        savings_pct = float(d.get("savings_pct") or 0)
        savings_eur = float(d.get("savings_eur") or 0)
        badge_color = "#16A34A" if savings_pct >= 15 else "#F59E0B" if savings_pct >= 8 else "#6B7280"
        cheap_src = _source_label(d.get("cheap_country"), d.get("cheap_provider"))
        expensive_src = _source_label(d.get("expensive_country"), d.get("expensive_provider"))
        cheap_url = d.get("cheap_url") or ""
        expensive_url = d.get("expensive_url") or ""
        cheap_link = f'<a href="{cheap_url}" style="font-size:11px; color:#15803D; text-decoration:underline;">View listing</a>' if cheap_url else ""
        expensive_link = f'<a href="{expensive_url}" style="font-size:11px; color:#991B1B; text-decoration:underline;">View listing</a>' if expensive_url else ""
        cheap_km = f"{int(d['cheap_km']):,} km" if d.get("cheap_km") else ""
        exp_km = f"{int(d['expensive_km']):,} km" if d.get("expensive_km") else ""

        deal_cards += f"""
        <div style="border:1px solid #E5E7EB; border-radius:8px; padding:12px; margin-bottom:8px;">
            <div style="display:flex; justify-content:space-between; align-items:baseline; flex-wrap:wrap; gap:4px;">
                <div>
                    <strong style="font-size:14px; color:#1A1A1A;">{d['make']} {d['model']}</strong>
                    <span style="color:#6B7280; font-size:12px;">{d.get('year') or ''}</span><br>
                    <span style="font-size:11px; color:#9CA3AF;">{int(d.get('listing_count') or 0)} listings &middot; {int(d.get('source_count') or 0)} sources</span>
                </div>
                <span style="background:{badge_color}; color:white; padding:2px 8px; border-radius:12px; font-size:12px; font-weight:600; white-space:nowrap;">
                    Save {_fmt_eur(savings_eur)} ({savings_pct:.0f}%)
                </span>
            </div>
            <!--[if mso]><table width="100%"><tr><td width="48%" valign="top"><![endif]-->
            <div style="display:inline-block; width:48%; vertical-align:top; min-width:140px; background:#F0FDF4; border-radius:6px; padding:8px; margin-top:8px; box-sizing:border-box;">
                <div style="font-size:10px; color:#16A34A; font-weight:600; text-transform:uppercase;">Cheapest</div>
                <div style="font-size:15px; font-weight:700; color:#15803D;">{_fmt_eur(d.get('cheap_price'))}</div>
                <div style="font-size:11px; color:#6B7280;">{cheap_src}{(' &middot; ' + cheap_km) if cheap_km else ''}</div>
                {cheap_link}
            </div>
            <!--[if mso]></td><td width="4%"></td><td width="48%" valign="top"><![endif]-->
            <div style="display:inline-block; width:48%; vertical-align:top; min-width:140px; background:#FEF2F2; border-radius:6px; padding:8px; margin-top:8px; box-sizing:border-box;">
                <div style="font-size:10px; color:#DC2626; font-weight:600; text-transform:uppercase;">Most Expensive</div>
                <div style="font-size:15px; font-weight:700; color:#991B1B;">{_fmt_eur(d.get('expensive_price'))}</div>
                <div style="font-size:11px; color:#6B7280;">{expensive_src}{(' &middot; ' + exp_km) if exp_km else ''}</div>
                {expensive_link}
            </div>
            <!--[if mso]></td></tr></table><![endif]-->
        </div>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="margin:0; padding:0; background:#F5F5F5; font-family:'Inter','Helvetica Neue',Arial,sans-serif; -webkit-text-size-adjust:100%;">
<div style="max-width:600px; margin:0 auto; padding:20px 12px;">

    <!-- Header -->
    <div style="text-align:center; padding:16px 0 20px;">
        <h1 style="color:#1A1A1A; font-size:22px; font-weight:700; margin:0; letter-spacing:-0.02em;">
            Car<span style="color:#6B7280;">Hero</span>
        </h1>
        <p style="color:#6B7280; font-size:14px; margin:6px 0 0;">Daily Deals &middot; {today}</p>
        <p style="color:#9CA3AF; font-size:12px; margin:4px 0 0;">Fresh picks from overnight European market scan</p>
    </div>

    {stats_html}
    {drops_html}
    {variant_html}

    <!-- Price Comparisons -->
    <div style="background:#FFFFFF; border:1px solid #E5E7EB; border-radius:8px; padding:16px; margin-bottom:20px;">
        <h2 style="color:#1A1A1A; font-size:16px; font-weight:600; margin:0 0 4px;">Best Price Arbitrage</h2>
        <p style="color:#6B7280; font-size:12px; margin:0 0 12px;">
            Same make &amp; model, different prices across countries and providers.
        </p>
        {deal_cards if deal_cards else '<p style="padding:16px; text-align:center; color:#6B7280;">No price differences found yet.</p>'}
    </div>

    <!-- Footer -->
    <div style="text-align:center; padding:16px 0; border-top:1px solid #E5E7EB; margin-top:8px;">
        <p style="color:#6B7280; font-size:12px; margin:0 0 4px;">
            <a href="{BASE_URL}/app" style="color:#000000; text-decoration:none; font-weight:600;">Open CarHero</a>
            &nbsp;&middot;&nbsp;
            <a href="{BASE_URL}/app/daily-scan" style="color:#000000; text-decoration:none;">Daily Scan</a>
            &nbsp;&middot;&nbsp;
            <a href="{BASE_URL}/app/market-map" style="color:#000000; text-decoration:none;">Market Map</a>
        </p>
        <p style="color:#9CA3AF; font-size:11px; margin:0;">
            Predictive Labs Ltd &middot; You're receiving this because you signed up for CarHero alerts.
        </p>
    </div>

</div>
</body>
</html>"""


def build_digest_text(
    comparisons: list[dict],
    price_drops: list[dict] | None = None,
    stats: dict | None = None,
    variant_comparisons: list[dict] | None = None,
) -> str:
    now = datetime.now()
    today = now.strftime("%A, %B %d, %Y")

    stats = stats or {}
    fresh = stats.get("fresh_count", 0)
    new_count = stats.get("new_count", 0)

    lines = [f"CarHero Daily Deals -- {today}", "=" * 44, ""]

    if fresh > 0:
        lines.append(f"  {fresh:,} listings refreshed | {new_count:,} new today")
        lines.append("")

    if price_drops:
        lines.append("PRICE DROPS")
        lines.append("-" * 44)
        for d in price_drops:
            drop_pct = float(d.get("drop_pct") or 0)
            lines.append(f"  {d['make']} {d['model']} {d.get('year') or ''}")
            lines.append(f"    Was {_fmt_eur(d.get('old_price'))} -> Now {_fmt_eur(d.get('price_eur'))} (down {drop_pct:.0f}%)")
        lines.append("")

    if variant_comparisons:
        lines.append("VERIFIED VARIANT DEALS")
        lines.append("-" * 44)
        for d in variant_comparisons:
            cheap_src = _source_label(d.get("cheap_country"), d.get("cheap_provider"))
            expensive_src = _source_label(d.get("expensive_country"), d.get("expensive_provider"))
            cheap_yr = f" ({d['cheap_year']})" if d.get("cheap_year") else ""
            exp_yr = f" ({d['expensive_year']})" if d.get("expensive_year") else ""
            cheap_km = f", {int(d['cheap_km']):,} km" if d.get("cheap_km") else ""
            exp_km = f", {int(d['expensive_km']):,} km" if d.get("expensive_km") else ""
            lines.append(f"  {d['canonical_variant']}  ({int(d.get('listing_count') or 0)} listings, median {_fmt_eur(d.get('median_price'))})")
            lines.append(f"    Cheapest:  {_fmt_eur(d.get('cheap_price'))} ({cheap_src}{cheap_yr}{cheap_km})")
            if d.get("cheap_url"):
                lines.append(f"               {d['cheap_url']}")
            lines.append(f"    Expensive: {_fmt_eur(d.get('expensive_price'))} ({expensive_src}{exp_yr}{exp_km})")
            if d.get("expensive_url"):
                lines.append(f"               {d['expensive_url']}")
            lines.append(f"    Save {_fmt_eur(d.get('savings_eur'))} ({float(d.get('savings_pct') or 0):.0f}%)")
            lines.append("")

    lines.append("BEST PRICE ARBITRAGE")
    lines.append("-" * 44)
    for d in comparisons:
        cheap_src = _source_label(d.get("cheap_country"), d.get("cheap_provider"))
        expensive_src = _source_label(d.get("expensive_country"), d.get("expensive_provider"))
        lines.append(f"  {d['make']} {d['model']} {d.get('year') or ''}  ({int(d.get('listing_count') or 0)} listings)")
        lines.append(f"    Cheapest:  {_fmt_eur(d.get('cheap_price'))} ({cheap_src})")
        if d.get("cheap_url"):
            lines.append(f"               {d['cheap_url']}")
        lines.append(f"    Expensive: {_fmt_eur(d.get('expensive_price'))} ({expensive_src})")
        if d.get("expensive_url"):
            lines.append(f"               {d['expensive_url']}")
        lines.append(f"    Save {_fmt_eur(d.get('savings_eur'))} ({float(d.get('savings_pct') or 0):.0f}%)")
        lines.append("")

    lines.append("---")
    lines.append(f"{BASE_URL}/app")
    return "\n".join(lines)
