from pricing.catalog import CATALOG_VERSION, catalogue_summary, load_municipal_catalog


def test_municipal_catalog_has_auditable_post_pilot_coverage():
    rows = load_municipal_catalog()
    summary = catalogue_summary(rows)
    assert CATALOG_VERSION == "eu-local-government-v1-2026-09-21"
    assert summary["entries"] == 110
    assert len(summary["sectors"]) == 10
    assert summary["goods"] >= 50
    assert summary["services"] >= 40
    assert summary["monitoring_tiers"]["web_price"] >= 50


def test_pilot_items_remain_in_expanded_catalogue():
    by_name = {row["name"]: row for row in load_municipal_catalog()}
    assert by_name["A4 80 gsm office copy paper, 500 sheets"]["cpv_code"] == "30197630"
    assert by_name["HP 207A black toner cartridge W2210A"]["identifier_value"] == "W2210A"
    assert by_name["Hourly technical computer support"]["cpv_code"] == "72611000"


def test_every_seed_entry_has_a_unique_official_cpv_mapping():
    rows = load_municipal_catalog()
    assert len({row["cpv_code"] for row in rows}) == len(rows)
    assert all(len(row["cpv_code"]) == 8 and row["cpv_code"].isdigit() for row in rows)
    assert all(row["cpv_label"] for row in rows)
    assert all(row["name_fr"] for row in rows)
