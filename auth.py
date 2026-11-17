"""Supabase Auth: client factory and startup check. (Routes are added in the next stages.)"""
import logging
from urllib.parse import urlparse

import httpx
from supabase import Client, create_client

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
