from evals.run_eval import score_answer


def test_french_answer_requires_french_and_clickable_source():
    case = {
        "requires_source": True,
        "requires_coverage_disclaimer": True,
        "expected_language": "fr",
    }
    good = score_answer(
        case,
        "Le prix observé provient de [Fournisseur](https://example.com/offre). "
        "La couverture n’est pas exhaustive.",
    )
    assert all(good.values())

    wrong_language = score_answer(
        case,
        "Observed price from [Supplier](https://example.com/offer). Coverage is not complete.",
    )
    assert wrong_language["answer_language"] is False


def test_plain_https_url_is_clickable_in_marked_renderer():
    case = {"requires_source": True, "requires_coverage_disclaimer": False}
    checks = score_answer(case, "Observed source https://example.com/offer")
    assert checks["source_provenance"] is True
    assert checks["clickable_source"] is True
