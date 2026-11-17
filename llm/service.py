"""The /triage logic. Stage 2: calls the model and returns its raw text (validation arrives in Stage 3)."""
from fastapi import HTTPException

import config
from llm import client
from llm.prompts import load_system_prompt, user_message
from llm.schema import STUB_RESULT


def classify(text: str):
    if config.LLM_STUB:
        return STUB_RESULT
    if not config.llm_configured():
        raise HTTPException(
            status_code=503,
            detail="No LLM provider configured. Set LLM_BASE_URL, LLM_API_KEY and LLM_MODEL (or LLM_STUB=1).",
        )
    system, _version = load_system_prompt()
    raw = client.complete(system, user_message(text))
    return {"model_said": raw}  # Stage 2 only
