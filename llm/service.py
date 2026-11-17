"""The /triage logic. Stage 1: stub mode only; the model is wired in at Stage 2."""
import config
from fastapi import HTTPException

from llm.schema import STUB_RESULT, TriageResult


def classify(text: str) -> TriageResult:
    if config.LLM_STUB:
        return STUB_RESULT
    raise HTTPException(status_code=501, detail="The model is not connected yet. Set LLM_STUB=1 to use stub mode.")
