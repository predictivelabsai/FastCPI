"""LangChain tools for provenance-first FastCPI price searches."""

from __future__ import annotations

import json

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from pricing.service import search_web_prices


class WebPriceArgs(BaseModel):
    query: str = Field(description="Product, service, CPV code, SKU, MPN or GTIN to price")
    market: str = Field(description="Two-letter FastCPI market code, for example FR or DE")
    limit: int = Field(default=8, ge=1, le=15)


def _search_web_prices(**kwargs) -> str:
    args = WebPriceArgs(**kwargs)
    result = search_web_prices(args.query, args.market, limit=args.limit, fetch_pages=True)
    artifact = {
        "kind": "prices", "title": f"Observed prices · {args.market.upper()}",
        "subtitle": result["coverage_statement"], "offers": result["offers"],
        "discoveries": result["discovery_only"],
    }
    lines = [result["coverage_statement"], ""]
    for offer in result["offers"]:
        lines.append(
            f"- {offer['title']}: {offer['amount']} {offer['currency']} per {offer.get('comparable_unit') or offer.get('unit')} "
            f"({offer['url']}; captured {offer['captured_at']}; confidence {offer['confidence']:.0%})"
        )
    if not result["offers"]:
        lines.append("No candidate page yielded a structured, attributable price. Discovery-only pages are shown separately.")
    if result["discovery_only"]:
        lines.extend(["", "Discovery-only candidate URLs (no attributable price extracted):"])
        for candidate in result["discovery_only"][:8]:
            lines.append(f"- {candidate.get('title') or 'Candidate'}: {candidate.get('url')}")
    return f"__ARTIFACT__{json.dumps(artifact)}\n\n" + "\n".join(lines)


web_price_search = StructuredTool.from_function(
    func=_search_web_prices, name="web_price_search",
    description="Discover supplier pages with Exa, fetch them, extract structured prices, and preserve source evidence.",
    args_schema=WebPriceArgs,
)
