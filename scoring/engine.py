"""Core scoring engine — computes investment scores for car listings."""

from __future__ import annotations

import logging
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import text

from scoring.config import (
    WEIGHTS, TIER_THRESHOLDS, MIN_LISTINGS_FOR_BASELINE,
    FALLBACK_AVG_MILEAGE, FALLBACK_AVG_PRICE,
    DESIRABLE_TRANSMISSIONS, DESIRABLE_FUELS, DESIRABLE_BODY_TYPES,
    CONFIG_BONUSES,
)
from scoring.summary import build_summary

log = logging.getLogger(__name__)


def _fetch_listings(db, make: str | None = None) -> pd.DataFrame:
    conditions = ["status = 'active'", "price_eur > 0"]
    params = {}
    if make:
        conditions.append("make ILIKE :make")
        params["make"] = f"%{make}%"
    where = " AND ".join(conditions)
    sql = text(f"""
        SELECT id, make, model, year, price_eur, mileage_km,
               fuel_type, transmission, body_type, accident_free,
               service_history, country, provider
        FROM carhero.car_listings
        WHERE {where}
    """)
    rows = db.execute(sql, params).fetchall()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([dict(r._mapping) for r in rows])


def _fetch_baselines(db) -> pd.DataFrame:
    sql = text("""
        SELECT make, model, country,
               avg_price_eur, median_price_eur, avg_mileage_km, listing_count
        FROM carhero.market_snapshots
        WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM carhero.market_snapshots)
    """)
    rows = db.execute(sql).fetchall()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([dict(r._mapping) for r in rows])


def _compute_baselines_from_listings(df: pd.DataFrame) -> pd.DataFrame:
    grouped = df.groupby(["make", "model"]).agg(
        avg_price_eur=("price_eur", "mean"),
        median_price_eur=("price_eur", "median"),
        avg_mileage_km=("mileage_km", lambda x: x.dropna().mean()),
        listing_count=("id", "count"),
    ).reset_index()
    grouped["country"] = None
    return grouped


def _compute_depreciation(df: pd.DataFrame) -> pd.DataFrame:
    current_year = date.today().year
    yearly = df[df["year"].notna() & (df["year"] >= current_year - 10)].copy()
    if yearly.empty:
        return pd.DataFrame(columns=["make", "model", "retention_score"])

    yearly = yearly.groupby(["make", "model", "year"]).agg(
        avg_price=("price_eur", "mean"),
    ).reset_index()

    results = []
    for (make, model), group in yearly.groupby(["make", "model"]):
        if len(group) < 2:
            results.append({"make": make, "model": model, "retention_score": 50})
            continue
        group = group.sort_values("year")
        newest_price = group[group["year"] == group["year"].max()]["avg_price"].iloc[0]
        oldest_price = group[group["year"] == group["year"].min()]["avg_price"].iloc[0]
        year_span = group["year"].max() - group["year"].min()
        if oldest_price > 0 and year_span > 0:
            annual_retention = (newest_price / oldest_price) ** (1 / year_span)
            score = min(100, max(0, (annual_retention - 0.70) / 0.25 * 100))
        else:
            score = 50
        results.append({"make": make, "model": model, "retention_score": score})

    return pd.DataFrame(results)


def _score_listings(listings: pd.DataFrame, baselines: pd.DataFrame, depreciation: pd.DataFrame) -> pd.DataFrame:
    if baselines.empty:
        baselines = _compute_baselines_from_listings(listings)

    bl_global = baselines.groupby(["make", "model"]).agg(
        avg_price=("avg_price_eur", "mean"),
        avg_mileage=("avg_mileage_km", "mean"),
        total_listings=("listing_count", "sum"),
    ).reset_index()

    df = listings.merge(bl_global, on=["make", "model"], how="left")
    df["avg_price"] = df["avg_price"].fillna(FALLBACK_AVG_PRICE)
    df["avg_mileage"] = df["avg_mileage"].fillna(FALLBACK_AVG_MILEAGE)
    df["total_listings"] = df["total_listings"].fillna(10)

    # Price score: how underpriced vs market (centered at 50)
    df["price_ratio"] = df["price_eur"].astype(float) / df["avg_price"].replace(0, np.nan).fillna(FALLBACK_AVG_PRICE)
    df["price_score"] = ((1 - df["price_ratio"]) * 200 + 50).clip(0, 100).astype(int)
    df["price_vs_avg_pct"] = (1 - df["price_ratio"]) * 100

    # Mileage score: lower mileage = higher score (centered at 50)
    mileage_filled = df["mileage_km"].fillna(df["avg_mileage"])
    df["mileage_ratio"] = mileage_filled.astype(float) / df["avg_mileage"].replace(0, np.nan).fillna(FALLBACK_AVG_MILEAGE)
    df["mileage_score"] = ((1 - df["mileage_ratio"]) * 200 + 50).clip(0, 100).astype(int)
    df["mileage_vs_avg_pct"] = (1 - df["mileage_ratio"]) * 100

    # Scarcity score: fewer listings = rarer
    max_listings = df["total_listings"].max()
    if max_listings > 0:
        df["scarcity_score"] = ((1 - df["total_listings"] / max_listings) * 80 + 20).clip(0, 100).astype(int)
    else:
        df["scarcity_score"] = 50

    # Config desirability score
    df["config_score"] = 40  # base
    trans_mask = df["transmission"].isin(DESIRABLE_TRANSMISSIONS)
    df.loc[trans_mask, "config_score"] += CONFIG_BONUSES["transmission_auto"]
    fuel_mask = df["fuel_type"].isin(DESIRABLE_FUELS)
    df.loc[fuel_mask, "config_score"] += CONFIG_BONUSES["fuel_desirable"]
    body_mask = df["body_type"].isin(DESIRABLE_BODY_TYPES)
    df.loc[body_mask, "config_score"] += CONFIG_BONUSES["body_desirable"]
    accident_mask = df["accident_free"] == True
    df.loc[accident_mask, "config_score"] += CONFIG_BONUSES["accident_free"]
    service_mask = df["service_history"] == True
    df.loc[service_mask, "config_score"] += CONFIG_BONUSES["service_history"]
    df["config_score"] = df["config_score"].clip(0, 100)

    # Depreciation score
    df = df.merge(depreciation, on=["make", "model"], how="left")
    df["depreciation_score"] = df["retention_score"].fillna(50).astype(int)

    # Weighted total
    df["score"] = (
        df["price_score"] * WEIGHTS["price"]
        + df["mileage_score"] * WEIGHTS["mileage"]
        + df["depreciation_score"] * WEIGHTS["depreciation"]
        + df["scarcity_score"] * WEIGHTS["scarcity"]
        + df["config_score"] * WEIGHTS["config"]
    ).round(0).astype(int).clip(0, 100)

    # Tier
    df["tier"] = 3
    df.loc[df["score"] >= TIER_THRESHOLDS[2], "tier"] = 2
    df.loc[df["score"] >= TIER_THRESHOLDS[1], "tier"] = 1

    # Percentile within make/model
    df["percentile"] = df.groupby(["make", "model"])["score"].rank(pct=True, ascending=False) * 100
    df["percentile"] = df["percentile"].round(1)

    # Strength summary
    df["strength_summary"] = df.apply(
        lambda r: build_summary(
            r["price_score"], r["mileage_score"], r["depreciation_score"],
            r["scarcity_score"], r["config_score"],
            r.get("price_vs_avg_pct"), r.get("mileage_vs_avg_pct"),
        ), axis=1
    )

    return df


def _upsert_scores(db, df: pd.DataFrame, snapshot_date: date):
    if df.empty:
        return 0

    records = df[["id", "score", "tier", "percentile", "price_score", "mileage_score",
                   "depreciation_score", "scarcity_score", "config_score", "strength_summary"]].copy()
    records = records.rename(columns={"id": "listing_id"})
    records["snapshot_date"] = snapshot_date

    batch_size = 500
    total = 0
    for i in range(0, len(records), batch_size):
        batch = records.iloc[i:i + batch_size]
        for _, row in batch.iterrows():
            db.execute(text("""
                INSERT INTO carhero.investment_scores
                    (listing_id, score, tier, percentile, price_score, mileage_score,
                     depreciation_score, scarcity_score, config_score, strength_summary,
                     snapshot_date)
                VALUES
                    (:listing_id, :score, :tier, :percentile, :price_score, :mileage_score,
                     :depreciation_score, :scarcity_score, :config_score, :strength_summary,
                     :snapshot_date)
                ON CONFLICT (listing_id, snapshot_date) DO UPDATE SET
                    score = EXCLUDED.score,
                    tier = EXCLUDED.tier,
                    percentile = EXCLUDED.percentile,
                    price_score = EXCLUDED.price_score,
                    mileage_score = EXCLUDED.mileage_score,
                    depreciation_score = EXCLUDED.depreciation_score,
                    scarcity_score = EXCLUDED.scarcity_score,
                    config_score = EXCLUDED.config_score,
                    strength_summary = EXCLUDED.strength_summary,
                    computed_at = NOW()
            """), dict(row))
        total += len(batch)
    db.commit()
    return total


def compute_all_scores(snapshot_date: date | None = None) -> dict:
    from db import SessionLocal
    snapshot_date = snapshot_date or date.today()

    db = SessionLocal()
    try:
        listings = _fetch_listings(db)
        if listings.empty:
            log.warning("No active listings found")
            return {"scored": 0, "tiers": {}}

        baselines = _fetch_baselines(db)
        depreciation = _compute_depreciation(listings)
        scored = _score_listings(listings, baselines, depreciation)

        count = _upsert_scores(db, scored, snapshot_date)

        tier_counts = scored["tier"].value_counts().to_dict()
        log.info("Scored %d listings: Tier 1=%d, Tier 2=%d, Tier 3=%d",
                 count, tier_counts.get(1, 0), tier_counts.get(2, 0), tier_counts.get(3, 0))

        return {"scored": count, "tiers": tier_counts}
    finally:
        db.close()


def compute_scores_for_make(make: str, snapshot_date: date | None = None) -> dict:
    from db import SessionLocal
    snapshot_date = snapshot_date or date.today()

    db = SessionLocal()
    try:
        listings = _fetch_listings(db, make=make)
        if listings.empty:
            log.warning("No active listings for make=%s", make)
            return {"scored": 0, "tiers": {}}

        baselines = _fetch_baselines(db)
        depreciation = _compute_depreciation(listings)
        scored = _score_listings(listings, baselines, depreciation)

        count = _upsert_scores(db, scored, snapshot_date)

        tier_counts = scored["tier"].value_counts().to_dict()
        log.info("Scored %d %s listings", count, make)
        return {"scored": count, "tiers": tier_counts}
    finally:
        db.close()
