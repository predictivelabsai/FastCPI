from fasthtml.common import to_xml

from pages.access import access_page


def test_open_signup_is_reachable_in_french_with_google_and_email():
    html = to_xml(access_page("fr", "signup"))
    assert "/auth/google" in html
    assert "/auth/register" in html
    assert "Créer un compte" in html
    assert "6 caractères minimum" in html


def test_password_login_page_posts_to_login_route():
    html = to_xml(access_page("en", "login"))
    assert "/auth/login" in html
    assert "Continue with Google" in html
