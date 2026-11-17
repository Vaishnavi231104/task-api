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


def _to_task(row):
    """A database row -> the JSON shape the API has always returned (done is a real bool)."""
    return {"id": row["id"], "title": row["title"], "done": bool(row["done"])}


def list_tasks():
    with session() as conn:
        return [_to_task(r) for r in conn.execute("SELECT * FROM tasks")]


def get_task(task_id):
    """Return one task dict, or None if there is no such id."""
    with session() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return _to_task(row) if row else None


def create_task(title):
    """Insert a new, not-done task; the database assigns the id."""
    with session() as conn:
        cur = conn.execute("INSERT INTO tasks (title, done) VALUES (?, ?)", (title, 0))
        return {"id": cur.lastrowid, "title": title, "done": False}
