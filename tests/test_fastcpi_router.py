from agents.router import route


def test_routes_cpv_before_general_price_terms():
    assert route("show prices for CPV 30100000-0 in France") == "cpv_specialist"


def test_routes_identifiers_and_monitoring():
    assert route("price SKU ABC-123 in Germany") == "price_finder"
    assert route("watch A4 paper daily") == "watchlist_monitor"
    assert route("Monitor SKU ABC-123 in Germany every day") == "watchlist_monitor"


def test_routes_market_and_comparison():
    assert route("market: show the price index") == "market_analyst"
    assert route("compare: supplier A vs supplier B") == "product_compare"
