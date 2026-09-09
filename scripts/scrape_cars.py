"""CLI entry point for car listing scrapers.

Usage:
    python -m scripts.scrape_cars --provider autoscout24 --headless
    python -m scripts.scrape_cars --provider autotrader --headless --brand BMW
    python -m scripts.scrape_cars --all --headless
    python -m scripts.scrape_cars --load --provider autoscout24
    python -m scripts.scrape_cars --load --all
"""

from __future__ import annotations

import argparse
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("scrape")

PROVIDERS = [
    "autoscout24", "autotrader", "mobile_de", "autohero", "theparking",
    "auto24_ee", "auto24_lt", "auto24_lv", "blocket", "coches", "bilbasen",
    "nettiauto", "donedeal", "marktplaats", "otomoto", "standvirtual",
    "autovit", "finn", "collectingcars",
]


def get_scraper(provider: str):
    if provider == "autoscout24":
        from scripts.scrapers.autoscout24 import scrape
    elif provider == "autotrader":
        from scripts.scrapers.autotrader import scrape
    elif provider == "mobile_de":
        from scripts.scrapers.mobile_de import scrape
    elif provider == "autohero":
        from scripts.scrapers.autohero import scrape
    elif provider == "theparking":
        from scripts.scrapers.theparking import scrape
    elif provider == "auto24_ee":
        from scripts.scrapers.auto24 import scrape_ee as scrape
    elif provider == "auto24_lt":
        from scripts.scrapers.auto24 import scrape_lt as scrape
    elif provider == "auto24_lv":
        from scripts.scrapers.auto24 import scrape_lv as scrape
    elif provider == "blocket":
        from scripts.scrapers.blocket import scrape
    elif provider == "coches":
        from scripts.scrapers.coches import scrape
    elif provider == "bilbasen":
        from scripts.scrapers.bilbasen import scrape
    elif provider == "nettiauto":
        from scripts.scrapers.nettiauto import scrape
    elif provider == "donedeal":
        from scripts.scrapers.donedeal import scrape
    elif provider == "marktplaats":
        from scripts.scrapers.marktplaats import scrape
    elif provider == "otomoto":
        from scripts.scrapers.otomoto import scrape
    elif provider == "standvirtual":
        from scripts.scrapers.standvirtual import scrape
    elif provider == "autovit":
        from scripts.scrapers.autovit import scrape
    elif provider == "finn":
        from scripts.scrapers.finn import scrape
    elif provider == "collectingcars":
        from scripts.scrapers.collectingcars import scrape
    else:
        raise ValueError(f"Unknown provider: {provider}")
    return scrape


def load_to_db(provider: str):
    """Load scraped JSON data into carhero.car_listings.

    - New listings are inserted.
    - Existing listings (by source_url) get a price check: if price_eur
      changed, the old price is recorded in price_history and the listing
      is updated with the new price + refreshed scraped_at/updated_at.
    """
    from scripts.scrapers.base import load_checkpoint, listing_to_db_row
    from dotenv import load_dotenv
    load_dotenv()

    import os
    from sqlalchemy import create_engine, text

    engine = create_engine(os.environ["DB_URL"])

    listings = load_checkpoint(provider)
    if not listings:
        log.warning("No checkpoint data for %s", provider)
        return 0

    inserted = 0
    updated = 0
    unchanged = 0
    with engine.connect() as conn:
        for listing in listings:
            row = listing_to_db_row(listing)

            if row.get("source_url"):
                existing = conn.execute(
                    text("""SELECT id, price_eur FROM carhero.car_listings
                         WHERE source_url = :source_url
                         LIMIT 1"""),
                    {"source_url": row["source_url"]},
                ).fetchone()

                if existing:
                    old_id, old_price = existing
                    new_price = row.get("price_eur")

                    if old_price is not None and new_price is not None and float(old_price) != float(new_price):
                        conn.execute(
                            text("""INSERT INTO carhero.price_history
                                 (listing_id, price_eur) VALUES (:lid, :price)"""),
                            {"lid": old_id, "price": float(old_price)},
                        )
                        conn.execute(
                            text("""UPDATE carhero.car_listings
                                 SET price_eur = :price_eur,
                                     price_original = :price_original,
                                     mileage_km = COALESCE(:mileage_km, mileage_km),
                                     canonical_variant = COALESCE(:canonical_variant, canonical_variant),
                                     scraped_at = NOW(),
                                     updated_at = NOW(),
                                     status = 'active'
                                 WHERE id = :id"""),
                            {
                                "price_eur": new_price,
                                "price_original": row.get("price_original"),
                                "mileage_km": row.get("mileage_km"),
                                "canonical_variant": row.get("canonical_variant"),
                                "id": old_id,
                            },
                        )
                        updated += 1
                    else:
                        conn.execute(
                            text("""UPDATE carhero.car_listings
                                 SET scraped_at = NOW(), status = 'active'
                                 WHERE id = :id"""),
                            {"id": old_id},
                        )
                        unchanged += 1
                    continue

            conn.execute(
                text("""
                    INSERT INTO carhero.car_listings
                    (make, model, variant, generation,
                     price_eur, price_original, currency,
                     year, mileage_km, fuel_type, transmission, body_type,
                     engine_size_cc, power_hp, power_kw, torque_nm,
                     drive_type, steering_side, gears,
                     co2_grams, fuel_consumption_l100km, emission_class,
                     doors, seats, exterior_color, interior_color, interior_material,
                     condition, first_registration_date, owners_count,
                     accident_free, service_history,
                     features, equipment_packages,
                     source_url, provider, country, city,
                     seller_type, seller_name, listed_date,
                     image_urls, image_count, status, canonical_variant)
                    VALUES
                    (:make, :model, :variant, :generation,
                     :price_eur, :price_original, :currency,
                     :year, :mileage_km, :fuel_type, :transmission, :body_type,
                     :engine_size_cc, :power_hp, :power_kw, :torque_nm,
                     :drive_type, :steering_side, :gears,
                     :co2_grams, :fuel_consumption_l100km, :emission_class,
                     :doors, :seats, :exterior_color, :interior_color, :interior_material,
                     :condition, :first_registration_date, :owners_count,
                     :accident_free, :service_history,
                     :features, :equipment_packages,
                     :source_url, :provider, :country, :city,
                     :seller_type, :seller_name, :listed_date,
                     :image_urls, :image_count, :status, :canonical_variant)
                """),
                row,
            )
            inserted += 1

        conn.commit()

    log.info(
        "Loaded %s: %d inserted, %d price-updated, %d unchanged",
        provider, inserted, updated, unchanged,
    )
    return inserted


def main():
    ap = argparse.ArgumentParser(description="Scrape European car listing data")
    ap.add_argument("--provider", choices=PROVIDERS, help="Specific provider to scrape")
    ap.add_argument("--all", action="store_true", help="Scrape all providers")
    ap.add_argument("--brand", type=str, default=None, help="Specific brand to scrape (e.g. BMW)")
    ap.add_argument("--limit", type=int, default=0, help="Max listings per brand (0 = unlimited)")
    ap.add_argument("--headless", action="store_true", default=True, help="Run browser headless")
    ap.add_argument("--no-headless", dest="headless", action="store_false")
    ap.add_argument("--load", action="store_true", help="Load scraped JSON into DB instead of scraping")
    args = ap.parse_args()

    if not args.provider and not args.all:
        ap.error("Specify --provider or --all")

    providers = PROVIDERS if args.all else [args.provider]

    if args.load:
        total = 0
        for p in providers:
            total += load_to_db(p)
        log.info("Total loaded: %d listings", total)
        return

    for p in providers:
        log.info("=== Scraping %s ===", p.upper())
        try:
            scraper = get_scraper(p)
            scraper(headless=args.headless, limit=args.limit, brand=args.brand)
        except Exception as e:
            log.error("Failed scraping %s: %s", p, e, exc_info=True)
            if not args.all:
                sys.exit(1)

    log.info("Done.")


if __name__ == "__main__":
    main()
