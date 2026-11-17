"""Run the hand-labelled eval cases through a RUNNING /triage endpoint and report how many matched.

    python evals/run_eval.py                       # server on http://localhost:8000, 3.5 s between calls
    python evals/run_eval.py --url http://localhost:8000 --delay 3.5 --save

Needs the server running with a real model (LLM_STUB unset). On OpenRouter's free tier this spends
len(cases) of your 50 daily requests (more if a repair is needed), hence --delay (limit: 20 per minute).
Only needs the standard library, and only talks HTTP, so it works against any implementation.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

CASES_PATH = Path(__file__).resolve().parent / "cases.json"
RESULT_PATH = Path(__file__).resolve().parent / "last-run.json"


def load_cases(path: Path = CASES_PATH) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def call_triage(base_url: str, text: str, timeout: float = 90.0) -> tuple[int, dict | None]:
    request = urllib.request.Request(
        base_url.rstrip("/") + "/triage",
        data=json.dumps({"text": text}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        try:
            return err.code, json.loads(err.read().decode("utf-8"))
        except ValueError:
            return err.code, None


def score_case(case: dict, status: int, body: dict | None) -> dict:
    """Compare one answer with the label. The KEY field is `category`; priority is reported separately."""
    expected = case["expected"]
    result = {"id": case["id"], "kind": case["kind"], "text": case["text"], "status": status, "expected": expected, "got": body}
    if status != 200 or not isinstance(body, dict):
        result.update(category_ok=False, priority_ok=None, unsure_ok=None if "max_confidence" not in case else False)
        return result
    result["category_ok"] = body.get("category") == expected["category"]
    result["priority_ok"] = (body.get("priority") == expected["priority"]) if "priority" in expected else None
    if "max_confidence" in case:  # the "when unsure" rule: low confidence, not a confident guess
        result["unsure_ok"] = isinstance(body.get("confidence"), (int, float)) and body["confidence"] < case["max_confidence"]
    else:
        result["unsure_ok"] = None
    return result


def summarize(results: list[dict]) -> dict:
    total = len(results)
    category_hits = sum(1 for r in results if r["category_ok"])
    priority_scored = [r for r in results if r["priority_ok"] is not None]
    unsure_scored = [r for r in results if r["unsure_ok"] is not None]
    return {
        "cases": total,
        "category_correct": category_hits,
        "category_accuracy": round(100 * category_hits / total, 1) if total else 0.0,
        "priority_correct": sum(1 for r in priority_scored if r["priority_ok"]),
        "priority_scored": len(priority_scored),
        "when_unsure_held": sum(1 for r in unsure_scored if r["unsure_ok"]),
        "when_unsure_scored": len(unsure_scored),
        "failed_ids": [r["id"] for r in results if not r["category_ok"]],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--delay", type=float, default=3.5, help="seconds between calls (free tiers rate-limit)")
    parser.add_argument("--prompt-version", default="v1", help="label recorded with the result (set LLM_PROMPT_VERSION on the server to match)")
    parser.add_argument("--save", action="store_true", help=f"write {RESULT_PATH.name}")
    args = parser.parse_args(argv)

    cases = load_cases()
    results = []
    for index, case in enumerate(cases):
        if index:
            time.sleep(args.delay)
        status, body = call_triage(args.url, case["text"])
        result = score_case(case, status, body)
        results.append(result)
        got = (body or {}).get("category", "-") if status == 200 else f"HTTP {status}"
        mark = "ok  " if result["category_ok"] else "MISS"
        print(f"{mark} #{case['id']} [{case['kind']:9}] expected {case['expected']['category']:9} got {got}")

    summary = summarize(results)
    print()
    print(f"category (key field): {summary['category_correct']}/{summary['cases']} = {summary['category_accuracy']}%")
    print(f"priority            : {summary['priority_correct']}/{summary['priority_scored']}")
    print(f"when-unsure rule    : {summary['when_unsure_held']}/{summary['when_unsure_scored']} (category other AND confidence < 0.5)")
    if summary["failed_ids"]:
        print("failed cases        :", ", ".join(f"#{i}" for i in summary["failed_ids"]))
        for r in results:
            if not r["category_ok"]:
                print(f"  #{r['id']} {r['text']!r}\n      expected {r['expected']}  got HTTP {r['status']} {r['got']}")

    if args.save:
        record = {"date": date.today().isoformat(), "prompt_version": args.prompt_version, "url": args.url, "summary": summary, "results": results}
        RESULT_PATH.write_text(json.dumps(record, indent=2), encoding="utf-8")
        print(f"\nsaved {RESULT_PATH}")
    return 0 if not summary["failed_ids"] else 1


if __name__ == "__main__":
    sys.exit(main())
