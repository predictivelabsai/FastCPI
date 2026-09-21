from collections import Counter

from monitoring.cohort import cohort_specs


def test_monitoring_cohort_is_twenty_item_market_scans():
    cohort = cohort_specs()
    assert len(cohort) == 20
    assert set(Counter(row["catalogue_line_name"] for row in cohort).values()) == {2}
    assert len({row["identifier_value"] for row in cohort}) == 20
    assert all(len(row["default_market"]) == 2 for row in cohort)
