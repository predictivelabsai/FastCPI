from monitoring.starter import STARTER_WATCHLISTS
from pricing.identifiers import classify_query


def test_three_starter_watches_cover_good_sku_and_cpv_service():
    assert len(STARTER_WATCHLISTS) == 3
    assert [row["markets"] for row in STARTER_WATCHLISTS] == [["FR"], ["DE"], ["EE"]]
    assert [classify_query(row["query"]).kind for row in STARTER_WATCHLISTS] == [
        "text", "sku", "cpv",
    ]
