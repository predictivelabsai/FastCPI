from fasthtml.common import to_xml

from pages.developers import developers_page


def test_developer_page_links_all_documentation_formats_and_core_resources():
    html = to_xml(developers_page())
    for path in (
        "/api/docs", "/api/redoc", "/api/openapi/v1.json",
        "/api/openapi.json", "/swagger.json", "/api/v1/prices/search",
        "/api/v1/prices/observe", "/api/v1/cpv/{code}/overview",
    ):
        assert path in html
    assert "X-API-Key" in html
    assert "LLM and MCP discovery" in html
    assert "/mcp/" in html


def test_developer_page_has_complete_french_copy():
    html = to_xml(developers_page("fr"))
    for phrase in ("Plateforme développeurs", "Ressources API", "Découverte LLM et MCP", "Authentification"):
        assert phrase in html
