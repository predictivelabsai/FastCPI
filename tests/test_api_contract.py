"""Offline OpenAPI contract checks; no database connection is made."""

import os

os.environ.setdefault("DB_URL", "sqlite:///:memory:")

from api.app import create_app
from fastapi.testclient import TestClient


def test_fastcpi_openapi_exposes_core_price_contracts():
    schema = create_app().openapi()
    paths = schema["paths"]
    for path in (
        "/prices/search", "/prices/observe", "/prices/{observation_id}",
        "/observation-jobs", "/observation-jobs/{job_id}",
        "/items", "/cpv/search", "/cpv/{code}/overview",
        "/markets/{country}/overview", "/indices", "/watchlists", "/api-keys",
        "/watchlists/{watchlist_id}", "/watchlists/{watchlist_id}/run",
        "/watchlists/{watchlist_id}/runs", "/scan-runs/{scan_run_id}",
    ):
        assert path in paths
    assert schema["info"]["title"] == "FastCPI API"


def test_observation_is_write_and_persisted_search_is_get():
    paths = create_app().openapi()["paths"]
    assert "post" in paths["/prices/observe"]
    assert "get" in paths["/prices/search"]


def test_legacy_car_routes_are_not_exposed():
    paths = create_app().openapi()["paths"]
    for prefix in (
        "/favorites", "/saved-searches", "/garage", "/market-map",
        "/listings", "/analytics/query", "/daily-scan",
    ):
        assert not any(path.startswith(prefix) for path in paths)


def test_chat_requires_an_authenticated_user():
    response = TestClient(create_app()).post("/chat", json={"message": "test"})
    assert response.status_code == 401
