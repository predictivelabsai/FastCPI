"""Guard unambiguous FastHTML form-action routes."""

from fasthtml.common import fast_app

from auth.routes import register_auth_routes
from chat.watchlists import register_watchlist_routes


def _routes(register):
    app, rt = fast_app(secret_key="route-contract")
    register(rt)
    return [(route.path, set(route.methods or [])) for route in app.routes]


def test_email_registration_has_one_post_handler():
    matching = [methods for path, methods in _routes(register_auth_routes) if path == "/auth/register"]
    assert matching == [{"POST"}]


def test_watch_creation_does_not_collide_with_dynamic_detail_route():
    routes = _routes(register_watchlist_routes)
    assert ("/app/watchlist-create", {"POST"}) in routes
    assert not any(path == "/app/watchlists/create" for path, _ in routes)
