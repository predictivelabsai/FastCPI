"""Central registry of FastCPI specialist agents."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentSpec:
    slug: str
    name: str
    category: str
    icon: str
    one_liner: str
    description: str
    prefix: str
    example_prompts: tuple[str, ...] = field(default_factory=tuple)


CATEGORIES: list[dict] = [
    {"key": "search", "name": "Price Discovery", "blurb": "Find observed B2B prices with evidence.", "icon": "~"},
    {"key": "procurement", "name": "Procurement", "blurb": "Resolve CPV categories and comparable terms.", "icon": "#"},
    {"key": "market", "name": "Market Intelligence", "blurb": "Price distributions, trends and coverage.", "icon": "+"},
    {"key": "comparison", "name": "Comparison", "blurb": "Compare products, services and supplier offers.", "icon": "="},
    {"key": "monitoring", "name": "Monitoring", "blurb": "Create and review daily price watchlists.", "icon": "*"},
    {"key": "advisory", "name": "Advisory", "blurb": "Interpret evidence and procurement trade-offs.", "icon": "★"},
]


AGENTS: tuple[AgentSpec, ...] = (
    AgentSpec("price_finder", "Price Finder", "search", "~",
              "Find the lowest observed comparable prices and show their sources.",
              "Discovers public B2B supplier pages, extracts structured prices and separates evidence from discovery-only results.",
              "price:", ("price: A4 recycled printer paper in France", "price: SKU 6ES7214-1AG40-0XB0 in Germany", "price: GTIN 4006381333931 in the Netherlands")),
    AgentSpec("cpv_specialist", "CPV Specialist", "procurement", "#",
              "Search CPV Version 2008 divisions and all descendant categories.",
              "Resolves Common Procurement Vocabulary codes and turns broad divisions into evidence-led market searches.",
              "cpv:", ("cpv: 30100000-0 in France", "cpv: find descendants for office machinery", "cpv: compare cleaning services across Estonia and Latvia")),
    AgentSpec("market_analyst", "Market Analyst", "market", "+",
              "Explain price distributions, observed indices, sources and market coverage.",
              "Builds Plotly views from persisted observations while disclosing sample size, freshness and comparability limits.",
              "market:", ("market: office paper price trend in France", "market: compare observed prices across our ten markets", "market: show source coverage for IT services")),
    AgentSpec("product_compare", "Offer Compare", "comparison", "=",
              "Compare supplier offers on price, unit, VAT, delivery and evidence quality.",
              "Creates apples-to-apples comparisons and flags terms that prevent safe ranking.",
              "compare:", ("compare: copier lease offers in Germany and France", "compare: three lowest paper suppliers including delivery", "compare: SKU ABC-123 against equivalent products")),
    AgentSpec("watchlist_monitor", "Watchlist Monitor", "monitoring", "*",
              "Create daily monitors for products, services, CPV codes and SKUs.",
              "Turns a price question into a daily watch with target and percentage-change alerts.",
              "watch:", ("watch: A4 paper in France below EUR 3 per ream", "watch: CPV 72000000 across Germany and Estonia", "watch: alert me when SKU ABC-123 moves by 5%")),
    AgentSpec("advisor", "Procurement Advisor", "advisory", "★",
              "Turn observed market evidence into practical procurement decisions.",
              "Interprets price, coverage, supplier and commercial-term evidence without presenting FastCPI as an official CPI.",
              "advise:", ("advise: is this facilities-management quote competitive?", "advise: which market should we source laptops from?", "advise: what evidence should I attach to a benchmark report?")),
)

AGENTS_BY_SLUG: dict[str, AgentSpec] = {a.slug: a for a in AGENTS}


def by_slug(slug: str) -> AgentSpec | None:
    return AGENTS_BY_SLUG.get(slug)
