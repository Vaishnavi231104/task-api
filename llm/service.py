"""The /triage logic: call the model, treat its answer as untrusted, repair once, then give up cleanly."""
import time

from fastapi import HTTPException

import config
from llm import client
from llm.calllog import log_call
from llm.errors import LLMError
from llm.parsing import parse_and_validate
from llm.prompts import load_system_prompt, user_message
from llm.quarantine import quarantine
from llm.schema import STUB_RESULT, TriageResult

REPAIR_INSTRUCTION = (
    "Your previous answer was rejected for this reason: {error}. "
    "Return only corrected JSON matching the schema."
)


def classify(text: str) -> TriageResult:
    if config.LLM_STUB:
        return STUB_RESULT
    if not config.llm_configured():
        raise HTTPException(
            status_code=503,
            detail="No LLM provider configured. Set LLM_BASE_URL, LLM_API_KEY and LLM_MODEL (or LLM_STUB=1).",
        )

    system, version = load_system_prompt()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_message(text)},  # the note: user role only, JSON-encoded
    ]

    started = time.monotonic()
    calls: list[client.ChatResult] = []
    failed_attempts = 0
    repaired = False
    outcome = "ok"
    try:
        first = client.chat(messages)
        calls.append(first)
        result, error = parse_and_validate(first.text)
        if result is not None:
            return result

        # Repair ONCE: same prompt, plus the broken output, plus the exact error.
        repaired = True
        messages += [
            {"role": "assistant", "content": first.text},
            {"role": "user", "content": REPAIR_INSTRUCTION.format(error=error)},
        ]
        second = client.chat(messages)
        calls.append(second)
        result, error2 = parse_and_validate(second.text)
        if result is not None:
            return result

        # Give up cleanly: keep the evidence, tell the caller plainly, never return model text.
        outcome = "invalid_output"
        quarantine(
            text=text,
            error=f"first: {error} | after repair: {error2}",
            prompt_version=version,
            raw_outputs=[first.text, second.text],
        )
        raise HTTPException(
            status_code=422,
            detail="The model's answer did not match the expected format, even after one retry. Please try again.",
        )
    except LLMError as exc:  # timeout / rate limit / provider down / bad key: a clear status, never a crash
        outcome = exc.outcome
        failed_attempts = exc.attempts
        raise HTTPException(status_code=exc.http_status, detail=exc.public_message, headers=exc.headers) from exc
    finally:
        log_call(
            prompt_version=version,
            model=config.LLM_MODEL,
            input_tokens=sum(c.input_tokens or 0 for c in calls),
            output_tokens=sum(c.output_tokens or 0 for c in calls),
            duration_ms=int((time.monotonic() - started) * 1000),
            repaired=repaired,
            attempts=sum(c.attempts for c in calls) + failed_attempts,
            model_calls=len(calls),
            outcome=outcome,
            served_model=calls[-1].served_model if calls else None,
        )
