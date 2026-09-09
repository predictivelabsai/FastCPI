"""Generate human-readable strength summaries from component scores."""

from __future__ import annotations


def build_summary(
    price_score: int,
    mileage_score: int,
    depreciation_score: int,
    scarcity_score: int,
    config_score: int,
    price_vs_avg_pct: float | None = None,
    mileage_vs_avg_pct: float | None = None,
) -> str:
    parts = []

    if price_score >= 70 and price_vs_avg_pct is not None:
        parts.append(f"{abs(price_vs_avg_pct):.0f}% below market average")
    elif price_score >= 60:
        parts.append("priced below market average")
    elif price_score <= 30:
        parts.append("above market average price")

    if mileage_score >= 70 and mileage_vs_avg_pct is not None:
        parts.append(f"{abs(mileage_vs_avg_pct):.0f}% lower mileage than peers")
    elif mileage_score >= 60:
        parts.append("low mileage for age")
    elif mileage_score <= 30:
        parts.append("high mileage")

    if depreciation_score >= 70:
        parts.append("strong value retention")
    elif depreciation_score <= 30:
        parts.append("depreciates faster than average")

    if scarcity_score >= 70:
        parts.append("rare find")
    elif scarcity_score >= 50:
        parts.append("limited supply")

    if config_score >= 70:
        parts.append("desirable spec")

    if not parts:
        parts.append("average market positioning")

    return ", ".join(parts[:3]).capitalize()
