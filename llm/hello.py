"""Throwaway smoke test: can we get one word out of the model?   python llm/hello.py

Three environment variables are the ONLY difference between a model on your laptop (Ollama)
and one in a datacentre (OpenRouter): LLM_BASE_URL, LLM_API_KEY, LLM_MODEL.
"""
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    base_url=os.environ["LLM_BASE_URL"],
    api_key=os.environ["LLM_API_KEY"],
    timeout=30.0,  # never leave the SDK's 10-minute default
    max_retries=0,
)
res = client.chat.completions.create(
    model=os.environ["LLM_MODEL"],
    messages=[{"role": "user", "content": "Reply with exactly the word: ready"}],
)
print(res.choices[0].message.content)
