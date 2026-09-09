from auth.access import invite_only_enabled


def test_signup_is_open_by_default(monkeypatch):
    monkeypatch.delenv("INVITE_ONLY", raising=False)
    assert invite_only_enabled() is False


def test_invite_gate_can_be_explicitly_restored(monkeypatch):
    monkeypatch.setenv("INVITE_ONLY", "true")
    assert invite_only_enabled() is True
