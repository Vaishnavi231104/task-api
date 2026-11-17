# Stage 4: exploring SQLite by hand

These queries were run directly against `tasks.db` while the API server was
running, using Python's built-in `sqlite3` module (the SQL is identical to what
you would paste into the "Execute SQL" tab of DB Browser for SQLite).
After each change I called `GET /tasks` without restarting the server.

| Query | What it returned |
|---|---|
| `SELECT * FROM tasks;` | The 3 seeded rows (one of them, id 2, had been marked done through the API). |
| `SELECT * FROM tasks WHERE done = 1;` | Only the completed task: `(2, 'Build a CRUD API', 1)`. |
| `SELECT COUNT(*) FROM tasks;` | `3`: there were three tasks. |
| `UPDATE tasks SET done = 1;` | 3 rows affected. `GET /tasks` immediately showed all three with `"done": true`. |
| `DELETE FROM tasks WHERE done = 1;` | 3 rows affected. `GET /tasks` immediately returned `[]`. |

Takeaway: the API and the SQL client read and write the same file, so there is
one source of truth and nothing to sync.

Side note: because the seed runs whenever the table is empty, restarting the
server after that `DELETE` would insert the three example tasks again.
