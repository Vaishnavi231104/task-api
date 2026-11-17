"""A fake Supabase client so the auth routes can be tested without a Supabase project or network."""
import itertools
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from supabase import AuthApiError

import auth
from main import app


class FakeAuth:
    """Mimics the few supabase-py calls we use. Tokens are random-looking strings it remembers."""

    def __init__(self):
        self.users = {}      # email -> {"id", "password", "created_at"}
        self.tokens = {}     # access token -> email
        self.revoked = []    # tokens passed to admin.sign_out
        self.calls = []      # (method, token-or-None): lets tests check what was sent to Supabase
        self._ids = itertools.count(1)
        self.fail_with = None  # set to an Exception to simulate Supabase being down
        self.admin = SimpleNamespace(sign_out=self._admin_sign_out)

    def _maybe_fail(self):
        if self.fail_with is not None:
            raise self.fail_with

    def _user_obj(self, email):
        u = self.users[email]
        return SimpleNamespace(id=u["id"], email=email, created_at=u["created_at"])

    def sign_up(self, creds):
        self._maybe_fail()
        if len(creds["password"]) < 6:
            raise AuthApiError("Password should be at least 6 characters.", 422, "weak_password")
        if creds["email"] in self.users:
            raise AuthApiError("User already registered", 422, "user_already_exists")
        self.users[creds["email"]] = {
            "id": f"user-{next(self._ids)}",
            "password": creds["password"],
            "created_at": datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc),
        }
        return SimpleNamespace(user=self._user_obj(creds["email"]), session=None)

    def sign_in_with_password(self, creds):
        self._maybe_fail()
        user = self.users.get(creds["email"])
        if not user or user["password"] != creds["password"]:
            raise AuthApiError("Invalid login credentials", 400, "invalid_credentials")
        token = f"access-{len(self.tokens) + 1}.abc.def"
        self.tokens[token] = creds["email"]
        session = SimpleNamespace(
            access_token=token, refresh_token=f"refresh-{len(self.tokens)}", token_type="bearer", expires_in=3600
        )
        return SimpleNamespace(user=self._user_obj(creds["email"]), session=session)

    def get_user(self, jwt=None):
        self.calls.append(("get_user", jwt))
        self._maybe_fail()
        if jwt not in self.tokens:
            raise AuthApiError("invalid JWT: unable to parse or verify signature", 401, "bad_jwt")
        return SimpleNamespace(user=self._user_obj(self.tokens[jwt]))

    def _admin_sign_out(self, jwt, scope="global"):
        self.calls.append(("sign_out", jwt))
        self._maybe_fail()
        self.revoked.append(jwt)


@pytest.fixture
def fake():
    return SimpleNamespace(auth=FakeAuth())


@pytest.fixture
def client(fake):
    app.dependency_overrides[auth.supabase_client] = lambda: fake
    yield TestClient(app)  # no `with`: skips the startup hook (DB + Supabase ping)
    app.dependency_overrides.clear()


@pytest.fixture
def logged_in(client):
    """A signed-up, logged-in user: returns (access_token, email)."""
    client.post("/auth/signup", json={"email": "ada@example.com", "password": "password123"})
    token = client.post("/auth/login", json={"email": "ada@example.com", "password": "password123"}).json()["access_token"]
    return token, "ada@example.com"
