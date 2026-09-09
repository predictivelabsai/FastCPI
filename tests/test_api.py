"""Tests for the CarHero mobile API.

Run: pytest tests/test_api.py -v
Requires: server running on localhost:5010 with DB access.
"""

from __future__ import annotations

import json
import os
import time

import httpx
import pytest

BASE = os.environ.get("API_BASE", "http://localhost:5010/api/v1")
TIMEOUT = 60


@pytest.fixture(scope="module")
def client():
    return httpx.Client(base_url=BASE, timeout=TIMEOUT)


@pytest.fixture(scope="module")
def test_email():
    return f"apitest+{int(time.time())}@example.com"


@pytest.fixture(scope="module")
def auth_token(client, test_email):
    resp = client.post("/auth/register", json={
        "email": test_email,
        "password": "testpass123",
        "name": "Test User",
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "token" in data
    return data["token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Health ────────────────────────────────────────────────────────────

class TestHealth:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ── Auth ──────────────────────────────────────────────────────────────

class TestAuth:
    def test_register(self, client):
        email = f"reg+{int(time.time())}@example.com"
        resp = client.post("/auth/register", json={
            "email": email,
            "password": "pass123456",
            "name": "Reg User",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == email
        assert data["name"] == "Reg User"
        assert "token" in data
        assert data["user_id"] > 0

    def test_register_duplicate(self, client, auth_token, test_email):
        resp = client.post("/auth/register", json={
            "email": test_email,
            "password": "otherpass123",
        })
        assert resp.status_code == 409

    def test_login(self, client, test_email):
        resp = client.post("/auth/login", json={
            "email": test_email,
            "password": "testpass123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == test_email
        assert "token" in data

    def test_login_wrong_password(self, client, test_email):
        resp = client.post("/auth/login", json={
            "email": test_email,
            "password": "wrongpass",
        })
        assert resp.status_code == 401

    def test_login_unknown_email(self, client):
        resp = client.post("/auth/login", json={
            "email": "nobody@nowhere.com",
            "password": "whatever",
        })
        assert resp.status_code == 401

    def test_me(self, client, auth_token, test_email):
        resp = client.get("/auth/me", headers=auth_headers(auth_token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == test_email
        assert data["name"] == "Test User"
        assert data["user_id"] > 0

    def test_me_no_token(self, client):
        resp = client.get("/auth/me")
        assert resp.status_code == 401

    def test_me_bad_token(self, client):
        resp = client.get("/auth/me", headers=auth_headers("garbage.token.here"))
        assert resp.status_code == 401


# ── Agents ────────────────────────────────────────────────────────────

class TestAgents:
    def test_list_agents(self, client):
        resp = client.get("/agents")
        assert resp.status_code == 200
        agents = resp.json()
        assert len(agents) >= 5
        slugs = {a["slug"] for a in agents}
        assert "car_search" in slugs
        assert "market_analyst" in slugs
        assert "valuator" in slugs
        assert "car_compare" in slugs
        assert "advisor" in slugs

    def test_agent_fields(self, client):
        resp = client.get("/agents")
        agent = resp.json()[0]
        assert all(k in agent for k in ["slug", "name", "category", "icon", "one_liner", "prefix", "example_prompts"])
        assert len(agent["example_prompts"]) > 0


# ── Sessions ──────────────────────────────────────────────────────────

class TestSessions:
    def test_list_empty(self, client, auth_token):
        resp = client.get("/sessions", headers=auth_headers(auth_token))
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_requires_auth(self, client):
        resp = client.get("/sessions")
        assert resp.status_code == 401

    def test_get_nonexistent(self, client, auth_token):
        resp = client.get("/sessions/999999", headers=auth_headers(auth_token))
        assert resp.status_code == 404

    def test_delete_nonexistent(self, client, auth_token):
        resp = client.delete("/sessions/999999", headers=auth_headers(auth_token))
        assert resp.status_code == 404


# ── Chat ──────────────────────────────────────────────────────────────

class TestChat:
    def _stream_chat(self, client, auth_token, message, session_id=None):
        body = {"message": message}
        if session_id:
            body["session_id"] = session_id

        events = []
        with client.stream("POST", "/chat", json=body,
                           headers=auth_headers(auth_token)) as resp:
            assert resp.status_code == 200
            for line in resp.iter_lines():
                if line.startswith("event: "):
                    event_name = line[7:]
                elif line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                    except json.JSONDecodeError:
                        data = line[6:]
                    events.append({"event": event_name, "data": data})
        return events

    def test_search_query(self, client, auth_token):
        events = self._stream_chat(client, auth_token, "search: BMW X5 under 30k")

        event_types = [e["event"] for e in events]
        assert "session" in event_types, "Should emit session event"
        assert "agent_route" in event_types, "Should emit agent_route event"
        assert "done" in event_types, "Should emit done event"

        session_event = next(e for e in events if e["event"] == "session")
        assert "sid" in session_event["data"]

        route_event = next(e for e in events if e["event"] == "agent_route")
        assert route_event["data"]["slug"] == "car_search"

        token_events = [e for e in events if e["event"] == "token"]
        assert len(token_events) > 0, "Should stream response tokens"

    def test_market_query(self, client, auth_token):
        events = self._stream_chat(client, auth_token, "market: Audi Q5 price trends")

        route_event = next(e for e in events if e["event"] == "agent_route")
        assert route_event["data"]["slug"] == "market_analyst"
        assert any(e["event"] == "done" for e in events)

    def test_valuation_query(self, client, auth_token):
        events = self._stream_chat(client, auth_token, "value: 2020 Mercedes C300 45k km")

        route_event = next(e for e in events if e["event"] == "agent_route")
        assert route_event["data"]["slug"] == "valuator"
        assert any(e["event"] == "done" for e in events)

    def test_compare_query(self, client, auth_token):
        events = self._stream_chat(client, auth_token, "compare: BMW X3 vs Audi Q5")

        route_event = next(e for e in events if e["event"] == "agent_route")
        assert route_event["data"]["slug"] == "car_compare"
        assert any(e["event"] == "done" for e in events)

    def test_advisor_query(self, client, auth_token):
        events = self._stream_chat(client, auth_token, "advise: family SUV under 40k EUR")

        route_event = next(e for e in events if e["event"] == "agent_route")
        assert route_event["data"]["slug"] == "advisor"
        assert any(e["event"] == "done" for e in events)

    def test_session_continuity(self, client, auth_token):
        events1 = self._stream_chat(client, auth_token, "search: Audi A4 under 20k")
        sid = next(e for e in events1 if e["event"] == "session")["data"]["sid"]

        events2 = self._stream_chat(client, auth_token, "what about the diesel ones?", session_id=sid)
        sid2 = next(e for e in events2 if e["event"] == "session")["data"]["sid"]
        assert sid2 == sid, "Should reuse same session"

    def test_chat_requires_auth(self, client):
        resp = client.post("/chat", json={"message": "hello"})
        assert resp.status_code == 401

    def test_chat_empty_message(self, client, auth_token):
        resp = client.post("/chat", json={"message": ""},
                           headers=auth_headers(auth_token))
        assert resp.status_code == 422


# ── Session CRUD after chat ───────────────────────────────────────────

class TestSessionCRUD:
    def test_session_lifecycle(self, client, auth_token):
        # Create session via chat
        events = []
        with client.stream("POST", "/chat",
                           json={"message": "search: Volvo XC60 under 35k"},
                           headers=auth_headers(auth_token)) as resp:
            for line in resp.iter_lines():
                if line.startswith("event: "):
                    event_name = line[7:]
                elif line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                    except json.JSONDecodeError:
                        data = line[6:]
                    events.append({"event": event_name, "data": data})

        sid = next(e for e in events if e["event"] == "session")["data"]["sid"]

        # List sessions — should include new one
        resp = client.get("/sessions", headers=auth_headers(auth_token))
        assert resp.status_code == 200
        sessions = resp.json()
        sids = [s["id"] for s in sessions]
        assert sid in sids

        # Get session detail
        resp = client.get(f"/sessions/{sid}", headers=auth_headers(auth_token))
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["id"] == sid
        assert len(detail["messages"]) >= 2

        # Share session
        resp = client.post(f"/sessions/{sid}/share", headers=auth_headers(auth_token))
        assert resp.status_code == 200
        share = resp.json()
        assert "token" in share
        assert share["url"].startswith("/shared/")

        # Delete session
        resp = client.delete(f"/sessions/{sid}", headers=auth_headers(auth_token))
        assert resp.status_code == 200

        # Verify deleted
        resp = client.get(f"/sessions/{sid}", headers=auth_headers(auth_token))
        assert resp.status_code == 404
