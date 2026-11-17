"""POST /triage: one messy note in, one validated JSON answer out. Not a chatbot: no memory, no conversation."""
from fastapi import APIRouter, Response

import config
from llm import service
from llm.schema import FALLBACK_RESULT, TriageIn, TriageResult

router = APIRouter()


@router.post(
    "/triage",
    response_model=TriageResult,
    tags=["triage"],
    summary="Classify a messy to-do note",
    description="Sends the note to a language model and returns a **validated** category, priority, "
    "confidence and one-sentence reason. The answer always matches the schema, or the request fails with "
    "a clear error: raw model text is never returned.",
    responses={
        400: {"description": "`text` is missing, not a string, blank, or longer than 2000 characters (no model call is made)"},
        422: {"description": "The model's answer failed validation even after one repair attempt"},
        502: {"description": "The model provider failed or rejected this server's credentials (never retried on 401/403)"},
        503: {"description": "No provider configured, or the provider is rate-limiting us (see Retry-After)"},
        504: {"description": "The model did not answer within the timeout"},
    },
)
def triage(body: TriageIn, response: Response):
    if not config.LLM_ENABLED:  # KILL SWITCH: LLM_ENABLED=false. No model call, no deploy needed.
        response.headers["X-LLM-Fallback"] = "disabled"
        return FALLBACK_RESULT
    return service.classify(body.text)
