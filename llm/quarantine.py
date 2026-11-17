"""Answers that failed validation are kept for a human to look at, never returned to the caller."""
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

QUARANTINE_PATH = Path(__file__).resolve().parent.parent / "logs" / "quarantine.jsonl"
_lock = threading.Lock()
_MAX_RAW = 4000


def quarantine(*, text: str, error: str, prompt_version: str, raw_outputs: list[str]) -> None:
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "prompt_version": prompt_version,
        "input": text,
        "error": error,
        "raw_outputs": [r[:_MAX_RAW] for r in raw_outputs],
    }
    with _lock:
        QUARANTINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with QUARANTINE_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
