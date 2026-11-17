"""Auth route tests against a fake Supabase client. Run:  pytest"""
from supabase import AuthRetryableError

CREDS = {"email": "ada@example.com", "password": "password123"}


# ---- Stage 1: signup and login ------------------------------------------------

def test_signup_returns_201_and_safe_user(client):
    r = client.post("/auth/signup", json=CREDS)
    assert r.status_code == 201
    assert set(r.json()) == {"id", "email", "created_at"}
    assert "password" not in r.text


def test_signup_missing_or_empty_fields_is_400(client):
    for body in ({}, {"email": "a@b.co"}, {"password": "x"}, {"email": "", "password": ""}, {"email": "  ", "password": "pw"}):
        r = client.post("/auth/signup", json=body)
        assert r.status_code == 400, body
        assert "error" in r.json()


def test_signup_wrong_types_or_bad_json_is_400(client):
    assert client.post("/auth/signup", json={"email": 1, "password": 2}).status_code == 400
    assert client.post("/auth/signup", content=b"{oops", headers={"Content-Type": "application/json"}).status_code == 400


def test_signup_rejected_by_supabase_is_400_with_its_message(client):
    assert client.post("/auth/signup", json=CREDS).status_code == 201
    dup = client.post("/auth/signup", json=CREDS)
    assert dup.status_code == 400 and "already registered" in dup.json()["error"]
    weak = client.post("/auth/signup", json={"email": "x@y.co", "password": "123"})
    assert weak.status_code == 400 and "error" in weak.json()


def test_login_returns_tokens(client):
    client.post("/auth/signup", json=CREDS)
    r = client.post("/auth/login", json=CREDS)
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"] and body["refresh_token"] and body["token_type"] == "bearer"


def test_login_empty_fields_is_400(client):
    assert client.post("/auth/login", json={}).status_code == 400
    assert client.post("/auth/login", json={"email": "a@b.co", "password": ""}).status_code == 400


def test_login_wrong_password_or_unknown_user_is_401_same_message(client):
    client.post("/auth/signup", json=CREDS)
    wrong = client.post("/auth/login", json={**CREDS, "password": "nope-nope"})
    unknown = client.post("/auth/login", json={"email": "ghost@example.com", "password": "password123"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"error": "Invalid login credentials"}


def test_supabase_down_is_502_not_a_crash_or_a_leak(client, fake):
    fake.auth.fail_with = AuthRetryableError("connection refused: secret-host", 0)
    for path in ("/auth/signup", "/auth/login"):
        r = client.post(path, json=CREDS)
        assert r.status_code == 502
        assert r.json() == {"error": "Authentication service unavailable"}


def test_not_configured_is_503_not_a_crash(monkeypatch):
    """No fake injected and no SUPABASE_* values: auth routes say so instead of crashing."""
    import config
    from fastapi.testclient import TestClient
    from main import app

    monkeypatch.setattr(config, "SUPABASE_URL", "")
    monkeypatch.setattr(config, "SUPABASE_KEY", "")
    r = TestClient(app).post("/auth/login", json=CREDS)
    assert r.status_code == 503
    assert "error" in r.json()
