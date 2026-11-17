"""A tiny fake OpenAI-compatible server for tests and offline checks.

Real HTTP, so the real `openai` SDK's timeouts and error handling are exercised, with no key and no cost.

    fake = FakeLLM().start()
    fake.say("ready")                       # next call answers 200 with this message content
    fake.fail(429, {"Retry-After": "3"})    # next call answers an error
    fake.slow(2.0, "ready")                 # next call waits 2 s first
    fake.requests                           # every request received: {"path", "headers", "body"}
"""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeLLM:
    def __init__(self, default="ready"):
        self.default = default
        self.script = []
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # keep test output quiet
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length) or b"{}")
                outer.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
                action = outer.script.pop(0) if outer.script else {"content": outer.default}
                if action.get("delay"):
                    time.sleep(action["delay"])
                status = action.get("status", 200)
                if status == 200:
                    payload = {
                        "id": "fake-1",
                        "object": "chat.completion",
                        "created": 0,
                        "model": body.get("model", "fake"),
                        "choices": [
                            {
                                "index": 0,
                                "finish_reason": "stop",
                                "message": {"role": "assistant", "content": action["content"]},
                            }
                        ],
                        "usage": {
                            "prompt_tokens": action.get("prompt_tokens", 100),
                            "completion_tokens": action.get("completion_tokens", 20),
                            "total_tokens": 120,
                        },
                    }
                else:
                    payload = {"error": {"message": action.get("message") or f"fake error {status}", "type": "fake_error"}}
                raw = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                for key, value in (action.get("headers") or {}).items():
                    self.send_header(key, value)
                self.end_headers()
                try:
                    self.wfile.write(raw)
                except OSError:  # the client already gave up (timeout tests)
                    pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self.httpd.server_address[1]}/v1"

    def start(self):
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def say(self, *contents, **extra):
        self.script += [{"content": c, **extra} for c in contents]

    def fail(self, status, headers=None, message=None):
        self.script.append({"status": status, "headers": headers, "message": message})

    def slow(self, seconds, content="ready"):
        self.script.append({"delay": seconds, "content": content})
