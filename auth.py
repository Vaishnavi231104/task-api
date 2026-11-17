"""Supabase Auth: client factory and startup check. (Routes are added in the next stages.)"""
import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, StrictStr
from supabase import (
    AuthApiError,
    AuthError,
    AuthInvalidCredentialsError,
    AuthWeakPasswordError,
    Client,
    create_client,
)

import config

log = logging.getLogger("uvicorn.error")


class AuthNotConfigured(Exception):
    """SUPABASE_URL / SUPABASE_KEY are missing."""


def get_supabase() -> Client:
    """Return a NEW Supabase client for each request.

    A shared client remembers the last user who logged in; creating one per
    request means one user's session can never leak into another request.
    """
    if not config.supabase_configured():
        raise AuthNotConfigured("SUPABASE_URL and SUPABASE_KEY are not set (see .env.example)")
    return create_client(config.SUPABASE_URL, config.SUPABASE_KEY)


def startup_check() -> None:
    """Log whether the Supabase project is reachable. Never raises: the Tasks API must still start."""
    if not config.supabase_configured():
        log.warning("Supabase not configured: copy .env.example to .env and fill it in. Auth routes will return 503.")
        return
    host = urlparse(config.SUPABASE_URL).netloc
    try:
        get_supabase()  # builds the client (no network call yet)
        resp = httpx.get(
            f"{config.SUPABASE_URL}/auth/v1/settings",
            headers={"apikey": config.SUPABASE_KEY},
            timeout=5,
        )
        if resp.status_code == 200:
            log.info("Server running and connected to Supabase (%s)", host)
        else:
            log.warning("Supabase answered HTTP %s for %s: check SUPABASE_URL and SUPABASE_KEY", resp.status_code, host)
    except Exception as exc:  # network down, bad URL, ...
        log.warning("Could not reach Supabase at %s: %s", host, type(exc).__name__)


# ---------------------------------------------------------------- models

class Credentials(BaseModel):
    email: Optional[StrictStr] = None
    password: Optional[StrictStr] = None


class UserOut(BaseModel):
    id: str
    email: Optional[str] = None
    created_at: Optional[datetime] = None


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: Optional[int] = None


class ErrorOut(BaseModel):
    error: str


BAD_REQUEST = {400: {"model": ErrorOut, "description": "Missing or rejected input"}}
UNAVAILABLE = {502: {"model": ErrorOut, "description": "Supabase could not be reached"}}


# ---------------------------------------------------------------- helpers

def supabase_client() -> Client:
    """FastAPI dependency: a fresh client per request (tests replace this with a fake)."""
    try:
        return get_supabase()
    except AuthNotConfigured:
        raise HTTPException(status_code=503, detail="Authentication is not configured on this server")


def _credentials(body: Credentials) -> tuple[str, str]:
    email = (body.email or "").strip()
    password = body.password or ""
    if not email or not password:
        raise HTTPException(status_code=400, detail="email and password are required")
    return email, password


def _upstream_failure(exc: Exception) -> HTTPException:
    """Supabase unreachable or misbehaving. Log the type only (never credentials or tokens)."""
    log.error("Supabase request failed: %s", type(exc).__name__)
    return HTTPException(status_code=502, detail="Authentication service unavailable")


# Parses "Authorization: Bearer <token>". auto_error=False so WE choose the 401 body and message.
bearer_scheme = HTTPBearer(auto_error=False, description="Paste the access_token returned by POST /auth/login")


def extract_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)) -> str:
    """Return the bearer token, or answer 401 if the header is missing, malformed, or has no token."""
    token = credentials.credentials.strip() if credentials else ""
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Access token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


# ---------------------------------------------------------------- routes

router = APIRouter()


@router.post(
    "/auth/signup",
    status_code=201,
    response_model=UserOut,
    responses={**BAD_REQUEST, **UNAVAILABLE},
    tags=["auth"],
    summary="Sign up",
    description="Creates a user account in Supabase Auth from `email` and `password`. "
    "Passwords are handled by Supabase; this server never stores or hashes them.",
)
def signup(body: Credentials, client: Client = Depends(supabase_client)):
    email, password = _credentials(body)
    try:
        result = client.auth.sign_up({"email": email, "password": password})
    except AuthApiError as exc:
        if exc.status >= 500:
            raise _upstream_failure(exc)
        raise HTTPException(status_code=400, detail=exc.message)  # e.g. weak password, already registered
    except AuthError as exc:
        if isinstance(exc, AuthWeakPasswordError):
            raise HTTPException(status_code=400, detail=exc.message)
        raise _upstream_failure(exc)
    except Exception as exc:
        raise _upstream_failure(exc)
    user = getattr(result, "user", None)
    if user is None:
        raise _upstream_failure(RuntimeError("no user in sign-up response"))
    return {"id": user.id, "email": user.email, "created_at": user.created_at}


@router.post(
    "/auth/login",
    response_model=TokenOut,
    responses={
        **BAD_REQUEST,
        401: {"model": ErrorOut, "description": "Invalid login credentials"},
        **UNAVAILABLE,
    },
    tags=["auth"],
    summary="Log in",
    description="Checks `email` and `password` with Supabase and returns the access token (a JWT) "
    "and refresh token. Send the access token as `Authorization: Bearer <token>` to protected routes.",
)
def login(body: Credentials, client: Client = Depends(supabase_client)):
    email, password = _credentials(body)
    try:
        result = client.auth.sign_in_with_password({"email": email, "password": password})
    except AuthApiError as exc:
        if exc.status == 429:
            raise HTTPException(status_code=429, detail="Too many attempts, try again later")
        if exc.status >= 500:
            raise _upstream_failure(exc)
        log.warning("Login rejected by Supabase: status=%s code=%s", exc.status, exc.code)
        raise HTTPException(status_code=401, detail="Invalid login credentials")
    except AuthError as exc:
        if isinstance(exc, (AuthInvalidCredentialsError, AuthWeakPasswordError)):
            raise HTTPException(status_code=401, detail="Invalid login credentials")
        raise _upstream_failure(exc)
    except Exception as exc:
        raise _upstream_failure(exc)
    session = getattr(result, "session", None)
    if session is None or not session.access_token:
        raise HTTPException(status_code=401, detail="Invalid login credentials")
    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "token_type": session.token_type or "bearer",
        "expires_in": session.expires_in,
    }


@router.get(
    "/public/info",
    tags=["public"],
    summary="Public info",
    description="Open to everyone. No token needed.",
)
def public_info():
    return {"message": "Welcome stranger! This info is public."}


@router.get(
    "/protected/profile",
    tags=["protected"],
    summary="My profile",
    description="Needs `Authorization: Bearer <token>`. (Stage 2: only checks that a token was sent; "
    "verification is added in the next stage.)",
)
def profile(token: str = Depends(extract_token)):
    return {"message": "A token was presented (not verified yet)."}
