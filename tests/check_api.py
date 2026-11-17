"""Black-box checks for the Task API (the A1 checkpoints, as a script).

Usage:  python tests/check_api.py [base_url]     (default http://localhost:8000)

It only talks HTTP, so it works against any storage behind the API. It creates
its own task and deletes it again, so it is safe to run repeatedly.
"""
import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8000"
failures = 0


def call(method, path, body=None, raw_body=None):
    data = raw_body if raw_body is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            status, text = resp.status, resp.read().decode()
    except urllib.error.HTTPError as err:
        status, text = err.code, err.read().decode()
    try:
        parsed = json.loads(text) if text else None
    except ValueError:
        parsed = None
    return status, parsed, text


def check(name, condition):
    global failures
    print(("PASS  " if condition else "FAIL  ") + name)
    if not condition:
        failures += 1


status, body, _ = call("GET", "/")
check("GET / -> 200 with name", status == 200 and body.get("name") == "Task API")
status, body, _ = call("GET", "/health")
check("GET /health -> 200 ok", status == 200 and body == {"status": "ok"})

status, tasks, _ = call("GET", "/tasks")
check("GET /tasks -> 200 list of {id,title,done}",
      status == 200 and isinstance(tasks, list) and all(set(t) == {"id", "title", "done"} for t in tasks))
status, body, _ = call("GET", "/tasks/999999")
check("GET /tasks/999999 -> 404 + error JSON", status == 404 and "error" in body)

status, body, _ = call("POST", "/tasks", {})
check("POST {} -> 400 + error JSON", status == 400 and "error" in body)
status, body, _ = call("POST", "/tasks", {"title": "   "})
check("POST blank title -> 400", status == 400 and "error" in body)
status, body, _ = call("POST", "/tasks", raw_body=b"{oops")
check("POST malformed JSON -> 400", status == 400 and "error" in body)

status, created, _ = call("POST", "/tasks", {"title": "Buy milk"})
check("POST valid -> 201, done=false, id is int",
      status == 201 and created["title"] == "Buy milk" and created["done"] is False and isinstance(created["id"], int))
tid = created["id"]
status, tasks, _ = call("GET", "/tasks")
check("GET /tasks lists the new task", any(t["id"] == tid for t in tasks))
status, body, _ = call("GET", f"/tasks/{tid}")
check("GET /tasks/{id} -> 200 same task", status == 200 and body == created)

status, body, _ = call("PUT", f"/tasks/{tid}", {})
check("PUT {} -> 400", status == 400 and "error" in body)
status, body, _ = call("PUT", f"/tasks/{tid}", {"title": ""})
check("PUT blank title -> 400", status == 400 and "error" in body)
status, body, _ = call("PUT", f"/tasks/{tid}", {"done": "yes"})
check("PUT done=\"yes\" -> 400", status == 400 and "error" in body)
status, body, _ = call("PUT", f"/tasks/{tid}", {"title": "Buy oat milk"})
check("PUT title -> 200 updated", status == 200 and body["title"] == "Buy oat milk" and body["done"] is False)
status, body, _ = call("PUT", f"/tasks/{tid}", {"done": True})
check("PUT done -> 200 keeps title", status == 200 and body["done"] is True and body["title"] == "Buy oat milk")
status, body, _ = call("PUT", "/tasks/999999", {"done": True})
check("PUT unknown id -> 404", status == 404 and "error" in body)

status, body, text = call("DELETE", f"/tasks/{tid}")
check("DELETE -> 204 with empty body", status == 204 and text == "")
status, body, _ = call("DELETE", f"/tasks/{tid}")
check("DELETE again -> 404", status == 404 and "error" in body)
status, body, _ = call("GET", f"/tasks/{tid}")
check("GET deleted task -> 404", status == 404)

print(f"\n{'ALL CHECKS PASSED' if failures == 0 else str(failures) + ' CHECK(S) FAILED'}")
sys.exit(1 if failures else 0)
