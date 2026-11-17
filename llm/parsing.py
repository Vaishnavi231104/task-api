"""Treat the model's answer as untrusted input: parse it, then validate it against the schema."""
import json
import re

from pydantic import ValidationError

from llm.schema import TriageResult

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_json_object(text: str) -> dict:
    """Pull the first JSON object out of the model's text.

    Models like to wrap JSON in a code fence or add "Sure! Here's the JSON:" in front.
    Raises ValueError (never anything else) if there is no usable object.
    """
    candidate = text.strip()
    fenced = _FENCE.search(candidate)
    if fenced:
        candidate = fenced.group(1).strip()

    decoder = json.JSONDecoder()
    for start, char in enumerate(candidate):
        if char != "{":
            continue
        try:
            obj, _end = decoder.raw_decode(candidate[start:])
        except ValueError:
            continue
        if isinstance(obj, dict):
            return obj
    raise ValueError("no JSON object found in the answer")


def describe_validation_error(exc: ValidationError) -> str:
    """A compact, exact description of what was wrong, e.g. "category: Input should be 'work', ... (got 'weather')"."""
    parts = []
    for err in exc.errors(include_url=False)[:5]:
        field = ".".join(str(p) for p in err["loc"]) or "(answer)"
        got = repr(err.get("input"))
        got = got if len(got) <= 40 else got[:37] + "..."
        parts.append(f"{field}: {err['msg']} (got {got})")
    return "; ".join(parts)


def parse_and_validate(raw: str) -> tuple[TriageResult | None, str | None]:
    """Return (result, None) if the raw text is a valid answer, else (None, a short error message)."""
    try:
        obj = extract_json_object(raw)
    except ValueError as exc:
        return None, str(exc)
    try:
        return TriageResult.model_validate(obj), None
    except ValidationError as exc:
        return None, describe_validation_error(exc)
