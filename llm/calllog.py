"""One structured log line per /triage request that reaches the model: what it cost and how long it took."""
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

CALL_LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "llm-calls.jsonl"
log = logging.getLogger("uvicorn.error")
_lock = threading.Lock()


def log_call(
    *,
    prompt_version: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    duration_ms: int,
    repaired: bool,
    attempts: int,
    model_calls: int,
    outcome: str,
    served_model: str | None = None,
) -> dict:
    """Record one request. Never includes the note, the answer or any key."""
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "prompt_version": prompt_version,
        "model": model,                # what we asked for
        "served_model": served_model,  # what the provider says answered (differs for routers)
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "duration_ms": duration_ms,
        "repaired": repaired,
        "attempts": attempts,        # HTTP attempts incl. retries
        "model_calls": model_calls,  # answers we got back (2 = needed a repair)
        "outcome": outcome,
    }
    line = json.dumps(record)
    log.info("LLM_CALL %s", line)
    try:
        with _lock:
            CALL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with CALL_LOG_PATH.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
    except OSError as exc:  # a full disk must not break the endpoint
        log.warning("could not write %s: %s", CALL_LOG_PATH, type(exc).__name__)
    return record
