"""Tests for the eval runner itself: does it score correctly? (It cannot grade a real model offline.)"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

from evals import run_eval
from tests.fake_llm import FakeLLM

CASES = run_eval.load_cases()


def test_there_are_eight_labelled_cases_including_unsure_and_hostile_ones():
    assert len(CASES) == 8 and len({c["id"] for c in CASES}) == 8
    kinds = {c["kind"] for c in CASES}
    assert {"clear", "unsure", "hostile", "ambiguous"} <= kinds
    for c in CASES:
        assert c["expected"]["category"] in {"work", "study", "personal", "health", "finance", "other"}
        assert 1 <= len(c["text"]) <= 2000


def test_eval_cases_do_not_reuse_the_prompts_examples():
    """If an eval text appears in the prompt, the score is inflated: the model has seen the answer."""
    prompt = open("prompts/triage-v1.md", encoding="utf-8").read().lower()
    for c in CASES:
        assert c["text"].lower() not in prompt, f"case #{c['id']} is quoted in the prompt"


def test_score_case_checks_category_priority_and_the_when_unsure_rule():
    clear = CASES[0]  # finance / high
    ok = run_eval.score_case(clear, 200, {"category": "finance", "priority": "high", "confidence": 0.9, "reason": "x"})
    assert ok["category_ok"] and ok["priority_ok"] and ok["unsure_ok"] is None
    wrong = run_eval.score_case(clear, 200, {"category": "work", "priority": "high", "confidence": 0.9, "reason": "x"})
    assert not wrong["category_ok"] and wrong["priority_ok"]
    unsure = next(c for c in CASES if c["kind"] == "unsure")
    confident_guess = run_eval.score_case(unsure, 200, {"category": "other", "priority": "normal", "confidence": 0.9, "reason": "x"})
    assert confident_guess["category_ok"] and confident_guess["unsure_ok"] is False   # right label, but it should not be so sure
    held = run_eval.score_case(unsure, 200, {"category": "other", "priority": "normal", "confidence": 0.2, "reason": "x"})
    assert held["category_ok"] and held["unsure_ok"] is True
    failed = run_eval.score_case(clear, 422, {"error": "x"})
    assert not failed["category_ok"] and failed["status"] == 422


def test_summarize_counts():
    results = [
        {"id": 1, "category_ok": True, "priority_ok": True, "unsure_ok": None},
        {"id": 2, "category_ok": False, "priority_ok": False, "unsure_ok": None},
        {"id": 3, "category_ok": True, "priority_ok": None, "unsure_ok": True},
        {"id": 4, "category_ok": True, "priority_ok": None, "unsure_ok": False},
    ]
    s = run_eval.summarize(results)
    assert (s["category_correct"], s["cases"], s["category_accuracy"]) == (3, 4, 75.0)
    assert (s["priority_correct"], s["priority_scored"]) == (1, 2)
    assert (s["when_unsure_held"], s["when_unsure_scored"]) == (1, 2)
    assert s["failed_ids"] == [2]


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _serve_with_fake(answers):
    fake = FakeLLM().start()
    for answer in answers:
        fake.say(json.dumps(answer))
    port = _free_port()
    env = dict(os.environ, LLM_BASE_URL=fake.base_url, LLM_API_KEY="k", LLM_MODEL="fake", LLM_STUB="0", LLM_ENABLED="true")
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--port", str(port)], env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1)
            break
        except Exception:
            time.sleep(0.25)
    return fake, server, f"http://127.0.0.1:{port}"


@pytest.mark.parametrize("right", [True, False])
def test_runner_end_to_end_against_a_real_server_and_a_fake_model(right, capsys):
    def answer_for(case):
        label = case["expected"]["category"] if right else "work" if case["expected"]["category"] != "work" else "study"
        return {"category": label, "priority": case["expected"].get("priority", "normal"),
                "confidence": 0.2 if "max_confidence" in case else 0.9, "reason": "test"}

    fake, server, url = _serve_with_fake([answer_for(c) for c in CASES])
    try:
        code = run_eval.main(["--url", url, "--delay", "0"])
    finally:
        server.terminate()
        fake.stop()
    out = capsys.readouterr().out
    if right:
        assert code == 0 and "category (key field): 8/8 = 100.0%" in out
    else:
        assert code == 1 and "category (key field): 0/8" in out and "failed cases" in out
