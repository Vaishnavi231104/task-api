"""The one place that talks to the model provider (any OpenAI-compatible API)."""
import time
from dataclasses import dataclass

from openai import OpenAI

import config


@dataclass
class ChatResult:
    text: str
    input_tokens: int | None
    output_tokens: int | None
    duration_ms: int


def make_client() -> OpenAI:
    return OpenAI(
        base_url=config.LLM_BASE_URL,
        api_key=config.LLM_API_KEY,
        timeout=config.LLM_TIMEOUT,  # explicit: the SDK default is ten minutes
        max_retries=0,               # explicit: no silent SDK retries (our own retry policy arrives in Stage 4)
    )


def chat(messages: list[dict]) -> ChatResult:
    """One model call. Returns the model's raw text plus what it cost."""
    started = time.monotonic()
    response = make_client().chat.completions.create(
        model=config.LLM_MODEL,
        temperature=0,  # same input, same answer: we want a label, not creativity
        messages=messages,
    )
    usage = getattr(response, "usage", None)
    return ChatResult(
        text=response.choices[0].message.content or "",
        input_tokens=getattr(usage, "prompt_tokens", None),
        output_tokens=getattr(usage, "completion_tokens", None),
        duration_ms=int((time.monotonic() - started) * 1000),
    )
