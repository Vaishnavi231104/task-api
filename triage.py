"""POST /triage: one messy note in, one validated JSON answer out. Not a chatbot: no memory, no conversation."""
from fastapi import APIRouter

from llm import service
from llm.schema import TriageIn, TriageResult

router = APIRouter()


@router.post(
    "/triage",
    # Stage 2 only: returns the model's raw text. Stage 3 puts response_model=TriageResult back.
    tags=["triage"],
    summary="Classify a messy to-do note",
    description="Sends the note to a language model and returns a **validated** category, priority, "
    "confidence and one-sentence reason. The answer always matches the schema, or the request fails with "
    "a clear error: raw model text is never returned.",
    responses={
        400: {"description": "`text` is missing, not a string, blank, or longer than 2000 characters (no model call is made)"},
        422: {"description": "The model's answer failed validation even after one repair attempt"},
        501: {"description": "Model not connected (use LLM_STUB=1)"},
    },
)
def triage(body: TriageIn):
    return service.classify(body.text)
