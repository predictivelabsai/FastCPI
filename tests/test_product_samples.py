from collections import Counter

from pricing.product_samples import SAMPLE_VERSION, load_product_samples, sample_summary


def test_product_samples_are_one_hundred_items_across_ten_lines():
    rows = load_product_samples()
    summary = sample_summary(rows)
    assert SAMPLE_VERSION == "eu-municipal-product-samples-v1-2026-09-21"
    assert summary["items"] == 100
    assert summary["catalogue_lines"] == 10
    assert set(Counter(row["catalogue_line_name"] for row in rows).values()) == {10}


def test_recommended_monitoring_cohort_contains_twenty_items():
    rows = load_product_samples()
    cohort = [row for row in rows if row["monitoring_cohort"] == "1"]
    assert len(cohort) == 20
    assert len({row["catalogue_line_name"] for row in cohort}) == 10
    assert all(row["source_url"].startswith("https://") for row in cohort)


def test_each_sample_has_a_unique_procurement_identifier_and_french_name():
    rows = load_product_samples()
    identifiers = {(row["identifier_type"], row["identifier_value"]) for row in rows}
    assert len(identifiers) == 100
    assert all(row["name_fr"] for row in rows)
