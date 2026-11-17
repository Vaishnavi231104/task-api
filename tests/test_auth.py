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


# ---- Stage 2: public route and the token-presence check -----------------------

def test_public_info_needs_no_token(client):
    r = client.get("/public/info")
    assert r.status_code == 200
    assert r.json() == {"message": "Welcome stranger! This info is public."}


def test_protected_without_a_usable_token_is_401(client):
    for headers in (
        {},                                    # no header at all
        {"Authorization": "Bearer"},           # scheme but no token
        {"Authorization": "Bearer "},          # scheme, blank token
        {"Authorization": "just-a-token"},     # no scheme: must NOT slip through
        {"Authorization": "Basic dXNlcjpwdw=="},  # wrong scheme
    ):
        r = client.get("/protected/profile", headers=headers)
        assert r.status_code == 401, headers
        assert r.json() == {"error": "Access token required"}
        assert r.headers["www-authenticate"] == "Bearer"


# ---- Stage 3: the guard verifies the token with Supabase ----------------------

def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_valid_token_returns_safe_user_metadata(client, logged_in):
    token, email = logged_in
    r = client.get("/protected/profile", headers=bearer(token))
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"id", "email", "created_at"}
    assert body["email"] == email


def test_token_is_sent_to_supabase_unchanged(client, fake, logged_in):
    token, _ = logged_in
    client.get("/protected/profile", headers=bearer(token))
    assert ("get_user", token) in fake.auth.calls


def test_tampered_token_is_401(client, logged_in):
    token, _ = logged_in
    tampered = token[:-1] + ("x" if token[-1] != "x" else "y")  # change one character
    r = client.get("/protected/profile", headers=bearer(tampered))
    assert r.status_code == 401
    assert r.json() == {"error": "Invalid or expired token"}


def test_garbage_token_is_401(client):
    r = client.get("/protected/profile", headers=bearer("not.a.jwt"))
    assert r.status_code == 401
    assert r.json() == {"error": "Invalid or expired token"}


def test_supabase_says_no_user_is_401(client, fake, logged_in):
    from types import SimpleNamespace
    fake.auth.get_user = lambda jwt=None: SimpleNamespace(user=None)
    token, _ = logged_in
    assert client.get("/protected/profile", headers=bearer(token)).status_code == 401
    fake.auth.get_user = lambda jwt=None: None
    assert client.get("/protected/profile", headers=bearer(token)).status_code == 401


def test_supabase_down_fails_closed_never_200(client, fake, logged_in):
    token, _ = logged_in
    fake.auth.fail_with = RuntimeError("boom")
    r = client.get("/protected/profile", headers=bearer(token))
    assert r.status_code == 502
    assert r.json() == {"error": "Authentication service unavailable"}


# ---- Stage 4: one reusable guard, logout --------------------------------------

def test_dashboard_reuses_the_guard(client, logged_in):
    token, email = logged_in
    assert client.get("/protected/dashboard").status_code == 401
    assert client.get("/protected/dashboard", headers=bearer("bad.token.here")).status_code == 401
    ok = client.get("/protected/dashboard", headers=bearer(token))
    assert ok.status_code == 200 and email in ok.json()["message"]


def test_every_protected_route_is_guarded(client):
    """Fails if someone adds a /protected/* route (or breaks logout) without the guard."""
    from main import app

    guarded = [
        (method.upper(), path)
        for path, ops in app.openapi()["paths"].items()
        if path.startswith("/protected") or path == "/auth/logout"
        for method in ops
    ]
    assert len(guarded) >= 3  # profile, dashboard, logout
    for method, path in guarded:
        assert client.request(method, path).status_code == 401, f"{method} {path} is not guarded"
        forged = client.request(method, path, headers=bearer("forged.token.value"))
        assert forged.status_code == 401, f"{method} {path} accepts a forged token"


def test_logout_without_or_with_bad_token_is_401_and_revokes_nothing(client, fake):
    assert client.post("/auth/logout").status_code == 401
    assert client.post("/auth/logout", headers=bearer("forged")).status_code == 401
    assert fake.auth.revoked == []


def test_logout_returns_204_empty_and_revokes_that_session(client, fake, logged_in):
    token, _ = logged_in
    r = client.post("/auth/logout", headers=bearer(token))
    assert r.status_code == 204
    assert r.content == b""
    assert fake.auth.revoked == [token]


def test_logout_when_supabase_fails_is_502(client, fake, logged_in):
    token, _ = logged_in
    fake.auth._admin_sign_out = None
    fake.auth.admin.sign_out = lambda jwt, scope="global": (_ for _ in ()).throw(RuntimeError("boom"))
    assert client.post("/auth/logout", headers=bearer(token)).status_code == 502
