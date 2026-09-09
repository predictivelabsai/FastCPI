from functools import lru_cache

from agents.base import build_agent
from agents.registry import AGENTS_BY_SLUG
from tools.prices import web_price_search

SPEC = AGENTS_BY_SLUG["product_compare"]


@lru_cache(maxsize=1)
def build():
    return build_agent(SPEC, [web_price_search])
