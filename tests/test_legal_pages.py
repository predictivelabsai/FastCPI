from fasthtml.common import to_xml

from pages.legal import delete_account_page, privacy_page


def test_privacy_page_discloses_core_mobile_data_flows():
    html = to_xml(privacy_page())

    assert "Predictive Labs Ltd" in html
    assert "AI chat prompts" in html
    assert "OpenAI or xAI" in html
    assert "Google Sign-In" in html
    assert "Postmark" in html
    assert 'href="/delete-account"' in html


def test_delete_account_page_has_in_app_and_web_request_paths():
    html = to_xml(delete_account_page())

    assert "Delete in the app" in html
    assert "Request deletion without the app" in html
    assert "mailto:info@carhero.chat" in html
