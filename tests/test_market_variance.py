from datetime import datetime, timezone

from api.app import create_app
from pricing.analytics import choose_default_market, summarize_markets, summarize_offers
from utils.fastcpi_i18n import app_catalog_item_name, app_tr


def _offer(market, price, domain, supplier=None):
    return {
        "market": market,
        "amount_comparable": price,
        "source_domain": domain,
        "supplier": supplier or domain,
        "unit_comparable": "each",
        "captured_at": datetime(2026, 9, 9, tzinfo=timezone.utc),
    }


def test_country_summary_measures_distinct_sources_and_price_spread():
    offers = [
        _offer("FR", 4.0, "supplier-a.fr"),
        _offer("FR", 6.0, "supplier-b.fr"),
        _offer("FR", 8.0, "supplier-c.fr"),
    ]
    summary = summarize_offers(offers)
    assert summary["source_count"] == 3
    assert summary["offer_count"] == 3
    assert summary["lowest"] == 4.0
    assert summary["median"] == 6.0
    assert summary["highest"] == 8.0
    assert summary["range"] == 4.0
    assert round(summary["spread_pct"], 1) == 66.7


def test_default_view_chooses_best_covered_country_and_prefers_france_on_tie():
    offers = [
        _offer("NL", 5.0, "one.nl"),
        _offer("NL", 6.0, "two.nl"),
        _offer("FR", 4.0, "one.fr"),
        _offer("FR", 7.0, "two.fr"),
        _offer("DE", 8.0, "one.de"),
    ]
    assert choose_default_market(offers) == "FR"
    rows = {row["market"]: row for row in summarize_markets(offers)}
    assert rows["FR"]["source_count"] == 2
    assert rows["DE"]["source_count"] == 1


def test_price_variance_api_is_discoverable():
    paths = create_app().openapi()["paths"]
    assert "/items/{item_id}/price-variance" in paths
    assert "get" in paths["/items/{item_id}/price-variance"]


def test_market_variance_copy_is_complete_in_french():
    assert app_tr("supplier_price_variance", "fr") == "Écart de prix entre fournisseurs"
    assert app_tr("within_country", "fr") == "Dans un même pays"
    assert app_tr("across_eu", "fr") == "Dans l’Union européenne"
    assert app_tr("supplier_source_evidence", "fr") == "Preuves des fournisseurs et des sources"
    assert app_catalog_item_name("Hourly technical computer support", "fr") == "Support informatique technique à l’heure"
