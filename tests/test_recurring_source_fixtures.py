from pathlib import Path

from pricing.extractors import extract_html


FIXTURES = Path(__file__).parent / "fixtures" / "extractors"


def _extract(name: str, url: str):
    return extract_html(url, (FIXTURES / name).read_text(encoding="utf-8"))


def test_gigaprint_paper_and_toner_fixtures_remain_extractable():
    paper = _extract("gigaprint-paper.html", "https://www.gigaprint.sk/paper")
    toner = _extract("gigaprint-toner.html", "https://www.gigaprint.sk/toner")
    assert (paper.amount, paper.currency, paper.sku) == (7.4, "EUR", "75355")
    assert (toner.amount, toner.currency, toner.sku) == (74, "EUR", "74793")
    assert paper.extraction_method == toner.extraction_method == "microdata"


def test_electrodepot_paper_fixture_remains_extractable():
    offer = _extract("electrodepot-paper.html", "https://www.electrodepot.fr/paper")
    assert offer.amount == 3.97
    assert offer.currency == "EUR"
    assert offer.extraction_method == "microdata"


def test_tender_level_offer_is_extractable_but_not_silently_a_product_fixture():
    offer = _extract("bidsfactory-tender.html", "https://bidsfactory.com/tender")
    assert offer.amount == 2_500_000
    assert offer.extraction_method == "json-ld"
    assert offer.title == "Computer workstation comprehensive service | BidsFactory"
