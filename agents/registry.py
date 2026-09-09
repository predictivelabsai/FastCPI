"""Central registry of all CarHero specialist agents."""

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
    {
        "key": "search",
        "name": "Car Search",
        "blurb": "Find and filter premium car listings across Europe.",
        "icon": "~",
    },
    {
        "key": "market",
        "name": "Market Intelligence",
        "blurb": "Price trends, depreciation curves, and geographic comparisons.",
        "icon": "#",
    },
    {
        "key": "advisory",
        "name": "Car Advisory",
        "blurb": "Valuations, comparisons, and personalized buying advice.",
        "icon": "+",
    },
    {
        "key": "personal",
        "name": "Your AI Car Hero",
        "blurb": "Your personal car advisor who finds deals and pushes you to act.",
        "icon": "★",
    },
]


AGENTS: tuple[AgentSpec, ...] = (
    # Search
    AgentSpec(
        slug="car_search", name="Car Search",
        category="search", icon="~", prefix="search:",
        one_liner="Find cars by make, model, price, year, mileage, and more.",
        description="Searches European car listings across AutoTrader UK, mobile.de, AutoScout24, and Autohero. Filters by make, model, price range, year, mileage, fuel type, transmission, and country.",
        example_prompts=(
            "search: BMW X5 under 40,000 EUR",
            "search: Tesla Model 3 in Germany, max 30k km",
            "search: Porsche 911 automatic, 2018 or newer",
            "search: Diesel SUVs under 25,000 EUR in the UK",
        ),
    ),
    # Market
    AgentSpec(
        slug="market_analyst", name="Market Analyst",
        category="market", icon="#", prefix="market:",
        one_liner="Price trends, depreciation curves, and market heat maps.",
        description="Analyzes car market trends including depreciation by model year, price distributions, geographic price differences, fuel type popularity, and segment performance. Generates charts and visualizations.",
        example_prompts=(
            "market: BMW 3 Series depreciation over model years",
            "market: average prices by brand across all listings",
            "market: diesel vs petrol price trends for SUVs",
            "market: which country has the cheapest Porsche Cayennes?",
        ),
    ),
    # Advisory
    AgentSpec(
        slug="valuator", name="Valuator",
        category="advisory", icon="+", prefix="value:",
        one_liner="Fair market value from comparable listings and trends.",
        description="Estimates the fair market value of a car using comparable listings, depreciation curves, mileage adjustments, and geographic pricing differences.",
        example_prompts=(
            "value: 2020 Mercedes C300, 45,000 km, Germany",
            "value: BMW 520d 2019 with 80k km, is 28,000 EUR fair?",
            "value: Audi Q5 2021, 35k km, petrol, automatic",
            "value: what should I pay for a 2018 Volvo XC60?",
        ),
    ),
    AgentSpec(
        slug="car_compare", name="Car Compare",
        category="advisory", icon="+", prefix="compare:",
        one_liner="Side-by-side comparison of models by price, specs, and value.",
        description="Compares two or more car models across dimensions like pricing, depreciation, specs, running costs, availability, and value for money.",
        example_prompts=(
            "compare: Audi Q5 vs BMW X3 vs Volvo XC60",
            "compare: Mercedes C-Class vs BMW 3 Series",
            "compare: Tesla Model 3 vs Audi A4 total cost",
            "compare: Porsche Macan vs Jaguar F-Pace",
        ),
    ),
    AgentSpec(
        slug="advisor", name="Car Advisor",
        category="advisory", icon="+", prefix="advise:",
        one_liner="Personalized buying recommendations based on your needs and budget.",
        description="Provides personalized car buying recommendations based on budget, use case, preferences, and market conditions. Considers depreciation, reliability, running costs, and value.",
        example_prompts=(
            "advise: EUR 50,000 budget, family SUV, Germany",
            "advise: best premium estate under 35k for long commutes",
            "advise: first luxury car for a young professional, 30k budget",
            "advise: reliable daily driver, diesel, under 20,000 EUR",
        ),
    ),
    # Personal
    AgentSpec(
        slug="kenri", name="Kenri",
        category="personal", icon="★", prefix="kenri:",
        one_liner="Your AI Car Hero -- finds deals, drops knowledge, pushes you to act.",
        description="Personal car advisor with a young commentator voice. Proactively surfaces deals, gives opinionated market takes, and keeps pushing you toward the best buys across 150,000+ European listings.",
        example_prompts=(
            "kenri: what's the best Porsche I can get for 100k?",
            "kenri: any sleeper deals on GT cars right now?",
            "kenri: I've got 50k and want something that turns heads",
            "kenri: what should I be buying before prices go up?",
        ),
    ),
)

AGENTS_BY_SLUG: dict[str, AgentSpec] = {a.slug: a for a in AGENTS}


def by_slug(slug: str) -> AgentSpec | None:
    return AGENTS_BY_SLUG.get(slug)
