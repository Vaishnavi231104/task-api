"""Prompts are code: they live in prompts/<job>-<version>.md, are versioned, reviewed and diffed."""
import json
from pathlib import Path

import config

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
JOB = "triage"


def load_system_prompt(version: str | None = None) -> tuple[str, str]:
    """Return (prompt text, version). The version is logged with every call."""
    version = version or config.LLM_PROMPT_VERSION
    path = PROMPT_DIR / f"{JOB}-{version}.md"
    return path.read_text(encoding="utf-8").strip(), version


def user_message(text: str) -> str:
    """The note goes in the USER message, never the system prompt, JSON-encoded so it cannot break
    out of its own quotes or pretend to be part of our instructions."""
    return json.dumps({"text": text}, ensure_ascii=False)
