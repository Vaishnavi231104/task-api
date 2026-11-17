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
