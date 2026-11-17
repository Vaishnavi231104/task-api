"""Settings read from environment variables (and a git-ignored .env file)."""
import os

from dotenv import load_dotenv

load_dotenv()  # reads .env next to where you run the app; real env vars win

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()  # the public *anon* key, never service_role
PORT = int(os.getenv("PORT", "8000"))


def supabase_configured() -> bool:
    placeholder = "your-project-ref" in SUPABASE_URL or SUPABASE_KEY in ("", "your_anon_key")
    return bool(SUPABASE_URL) and not placeholder


# ---- LLM (any OpenAI-compatible provider: OpenRouter, Ollama, ...) ----
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "").strip()
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() in ("1", "true", "yes", "on")


LLM_STUB = _flag("LLM_STUB", False)         # 1 = never call the model; return a hard-coded valid answer
LLM_ENABLED = _flag("LLM_ENABLED", True)    # false = kill switch: no model calls, deterministic fallback
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "30"))        # seconds per attempt (the SDK default is 600!)
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))   # our own retries; the SDK's are switched off
