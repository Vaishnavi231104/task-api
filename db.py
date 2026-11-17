"""Storage layer: everything that touches SQLite lives here."""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

# tasks.db sits next to this file (created automatically). Override with TASKS_DB.
DB_PATH = Path(os.environ.get("TASKS_DB", Path(__file__).parent / "tasks.db"))

SEED_TASKS = [
    ("Learn FastAPI", 0),
    ("Build a CRUD API", 0),
    ("Push to GitHub", 0),
]


@contextmanager
def session():
    """Open a connection; commit on success, roll back on error, always close."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create the table if missing and seed three tasks, but only into an empty table."""
    with session() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS tasks (
                   id    INTEGER PRIMARY KEY AUTOINCREMENT,
                   title TEXT NOT NULL,
                   done  INTEGER NOT NULL DEFAULT 0
               )"""
        )
        (count,) = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()
        if count == 0:
            # One transaction: either all three seed rows are saved, or none are.
            conn.executemany("INSERT INTO tasks (title, done) VALUES (?, ?)", SEED_TASKS)
