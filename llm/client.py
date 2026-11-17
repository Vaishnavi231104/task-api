"""The one place that talks to the model provider (any OpenAI-compatible API).

Timeout and retry policy (all explicit; nothing silent from the SDK):
  * per-attempt timeout: config.LLM_TIMEOUT seconds (max 60). The SDK default is ten minutes.
  * the SDK's own retries are OFF (max_retries=0); this module owns the policy, so one request
    can never quietly become six.
  * retry ONLY: timeouts, connection errors, 429 and 5xx. Never 400, 401, 403 (or other 4xx):
    a bad key is still a bad key in four seconds, and on a metered tier every retry burns quota.
  * backoff 1s, 2s, 4s ... plus jitter; a Retry-After header is obeyed instead of guessing.
"""
import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import openai
from openai import OpenAI

import config
from llm.errors import (
    LLMAuthError,
    LLMRateLimited,
    LLMRejected,
    LLMTimeout,
    LLMUnavailable,
)

log = logging.getLogger("uvicorn.error")

BASE_BACKOFF = 1.0       # seconds: 1, 2, 4, ...
MAX_WAIT = 30.0          # never hold a caller's request longer than this for one wait


@dataclass
class ChatResult:
    text: str
    input_tokens: int | None
    output_tokens: int | None
    duration_ms: int
    attempts: int
    served_model: str | None = None  # what the provider says actually answered (a router like openrouter/free varies)


def make_client() -> OpenAI:
    return OpenAI(
        base_url=config.LLM_BASE_URL,
        api_key=config.LLM_API_KEY,
        timeout=config.LLM_TIMEOUT,  # explicit: the SDK default is ten minutes
        max_retries=0,               # explicit: our own retry policy below, not the SDK's
    )


def _sleep(seconds: float) -> None:  # separate function so tests can replace it
    time.sleep(seconds)


def _jitter() -> float:
    return random.uniform(0.0, 0.5)


def _retry_after_seconds(exc: openai.APIStatusError) -> float | None:
    raw = exc.response.headers.get("retry-after")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        try:  # an HTTP date
            return max(0.0, (parsedate_to_datetime(raw) - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError):
            return None


def chat(messages: list[dict]) -> ChatResult:
    """One logical model call (with retries). Returns the raw text plus what it cost, or raises an LLMError."""
    client = make_client()
    started = time.monotonic()
    attempt = 0
    while True:
        attempt += 1
        retry_after = None
        try:
            response = client.chat.completions.create(
                model=config.LLM_MODEL,
                temperature=0,  # same input, same answer: we want a label, not creativity
                messages=messages,
            )
            usage = getattr(response, "usage", None)
            return ChatResult(
                text=response.choices[0].message.content or "",
                input_tokens=getattr(usage, "prompt_tokens", None),
                output_tokens=getattr(usage, "completion_tokens", None),
                duration_ms=int((time.monotonic() - started) * 1000),
                attempts=attempt,
                served_model=getattr(response, "model", None),
            )
        except openai.APITimeoutError:  # before APIConnectionError: it is a subclass
            kind, final = "timeout", LLMTimeout(attempts=attempt)
        except openai.APIConnectionError as exc:
            kind, final = f"connection error ({type(exc.__cause__).__name__})", LLMUnavailable(attempts=attempt)
        except openai.RateLimitError as exc:  # 429, before APIStatusError
            retry_after = _retry_after_seconds(exc)
            kind, final = "429 rate limited", LLMRateLimited(attempts=attempt, retry_after=retry_after)
        except openai.APIStatusError as exc:
            status = exc.status_code
            if status >= 500:
                kind, final = f"{status} server error", LLMUnavailable(attempts=attempt)
            elif status in (401, 403):
                log.error("LLM provider answered %s (credentials rejected). Not retrying.", status)
                raise LLMAuthError(f"HTTP {status}", attempts=attempt) from None
            else:  # 400, 404, 422, ...: our request is wrong; sending it again will not fix it
                log.error("LLM provider answered %s. Not retrying.", status)
                raise LLMRejected(f"HTTP {status}", attempts=attempt) from None

        # Only timeouts, connection errors, 429 and 5xx reach this point.
        if attempt > config.LLM_MAX_RETRIES:
            log.error("LLM call failed after %s attempt(s): %s", attempt, kind)
            raise final
        if retry_after is not None and retry_after > MAX_WAIT:
            log.error("LLM provider asked us to wait %.0fs; too long, giving up after %s attempt(s)", retry_after, attempt)
            raise final
        delay = retry_after if retry_after is not None else BASE_BACKOFF * 2 ** (attempt - 1) + _jitter()
        log.warning("LLM attempt %s failed (%s); retrying in %.1fs", attempt, kind, delay)
        _sleep(delay)
