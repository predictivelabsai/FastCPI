from agents.router import route, strip_prefix
from utils.fastcpi_i18n import APP_COPY, app_agent_name, app_agent_prompts, app_tr


def test_authenticated_workspace_copy_has_complete_french_values():
    assert APP_COPY
    assert all(len(values) == 2 and values[0] and values[1] for values in APP_COPY.values())
    assert app_tr("daily_scan", "fr") == "Analyse quotidienne"
    assert app_tr("watchlists", "fr") == "Listes de suivi"
    assert app_tr("account_api", "fr") == "Compte et clés API"


def test_french_agents_prompts_and_routing_are_native():
    prompts = app_agent_prompts("price_finder", (), "fr")
    assert prompts and "Prix" in prompts[0]
    assert app_agent_name("price_finder", "Price Finder", "fr") == "Recherche de prix"
    question = "Montrez-moi les prix du papier A4 recyclé en France"
    assert route(question) == "price_finder"
    assert strip_prefix(question) == question


def test_interface_language_does_not_change_user_question():
    english_question = "Show observed prices for A4 paper in France"
    assert strip_prefix(english_question) == english_question
