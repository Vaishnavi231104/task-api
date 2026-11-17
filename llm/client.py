"""The one place that talks to the model provider (any OpenAI-compatible API)."""
from openai import OpenAI

import config


def make_client() -> OpenAI:
    return OpenAI(
        base_url=config.LLM_BASE_URL,
        api_key=config.LLM_API_KEY,
        timeout=config.LLM_TIMEOUT,  # explicit: the SDK default is ten minutes
        max_retries=0,               # explicit: no silent SDK retries (retry policy arrives in Stage 4)
    )


def complete(system: str, user: str) -> str:
    """One model call. Returns the model's raw text."""
    response = make_client().chat.completions.create(
        model=config.LLM_MODEL,
        temperature=0,  # same input, same answer: we want a label, not creativity
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return response.choices[0].message.content or ""
