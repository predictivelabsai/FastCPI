from functools import lru_cache

from agents.base import build_agent
from agents.registry import AGENTS_BY_SLUG
from tools.listings import search_car_listings, car_stats
from tools.charts import market_treemap, price_trend, geographic_compare
from tools.deals import price_arbitrage
from tools.investment_score import investment_scores
from tools.search import web_search
from tools.sql_query import car_market_query

SPEC = AGENTS_BY_SLUG["kenri"]
TOOLS = [
    search_car_listings, car_stats, car_market_query,
    price_arbitrage, investment_scores,
    price_trend, market_treemap, geographic_compare,
    web_search,
]


@lru_cache(maxsize=1)
def build():
    return build_agent(SPEC, TOOLS)
