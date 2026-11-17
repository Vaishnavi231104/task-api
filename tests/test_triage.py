"""Tests for POST /triage (Stage 1: contract, validation, stub). Later stages append to this file."""
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import config
from llm.schema import MAX_TEXT, TriageResult
from main import app

VALID = {"text": "pay the electricity bill before friday"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(config, "LLM_STUB", True)
    return TestClient(app)  # no `with`: skips the startup hook


# ---- Stage 1: input validation (400 naming the field) ---------------------------

@pytest.mark.parametrize(
    "body",
    [
        {},                              # missing field
        {"text": None},                  # null
        {"text": 123},                   # wrong type
        {"text": ["a note"]},            # wrong type
        {"text": ""},                    # empty
        {"text": "   \n "},              # blank
        {"text": "x" * (MAX_TEXT + 1)},  # too long
    ],
)
def test_bad_input_is_400_and_names_the_field(client, body):
    r = client.post("/triage", json=body)
    assert r.status_code == 400
    assert "text" in r.json()["error"]


def test_text_at_the_limit_is_accepted(client):
    assert client.post("/triage", json={"text": "x" * MAX_TEXT}).status_code == 200


def test_malformed_json_is_400(client):
    r = client.post("/triage", content=b"{oops", headers={"Content-Type": "application/json"})
    assert r.status_code == 400 and "error" in r.json()


# ---- Stage 1: stub mode and the output schema -----------------------------------

def test_stub_mode_returns_schema_valid_json(client):
    r = client.post("/triage", json=VALID)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"category", "priority", "confidence", "reason"}
    TriageResult.model_validate(body)  # raises if it does not match the contract


def test_without_stub_and_without_a_model_it_says_so(monkeypatch):
    monkeypatch.setattr(config, "LLM_STUB", False)
    assert TestClient(app).post("/triage", json=VALID).status_code == 501


@pytest.mark.parametrize(
    "bad",
    [
        {"category": "weather", "priority": "low", "confidence": 0.5, "reason": "x"},          # not in the list
        {"category": "work", "priority": "urgent", "confidence": 0.5, "reason": "x"},          # not in the list
        {"category": "work", "priority": "low", "confidence": 1.5, "reason": "x"},             # out of range
        {"category": "work", "priority": "low", "confidence": "0.5", "reason": "x"},           # wrong type
        {"category": "work", "priority": "low", "confidence": True, "reason": "x"},            # bool is not a number here
        {"category": "work", "priority": "low", "confidence": 0.5, "reason": ""},              # empty
        {"category": "work", "priority": "low", "confidence": 0.5, "reason": "x" * 201},       # too long
        {"category": "work", "priority": "low", "confidence": 0.5, "reason": "x", "extra": 1}, # unknown field
        {"category": "work", "priority": "low", "confidence": 0.5},                            # missing field
    ],
)
def test_schema_rejects_everything_outside_the_contract(bad):
    with pytest.raises(ValidationError):
        TriageResult.model_validate(bad)
