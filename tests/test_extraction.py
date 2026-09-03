"""Tests for the model node, with the API replaced by a fake.

The fake returns canned LLMResult objects so the node's own logic is under
test: truncation, refusal, validation retry with the error fed back, and
the API error path. Nothing here touches the network.
"""

import json

import anthropic
import httpx
import pytest

from agents.statement_extraction import nodes
from agents.statement_extraction.nodes import node_extract_fields, node_finalize
from agents.statement_extraction.schema import ErrorCode, StatementData, normalise_date
from core.llm import LLMResult

GOOD = {
    "account_holder": "Jane Doe",
    "closing_balance": 1096.5,
    "account_number": "111",
    "statement_date": "2026-08-31",
    "currency": "usd",
    "bank_name": "ACME",
    "transactions": [{"date": "2026-08-01", "description": "Coffee", "amount": -3.5}],
}


def result(payload, stop_reason="end_turn", output_tokens=50):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return LLMResult(text=text, stop_reason=stop_reason, model="fake", input_tokens=100, output_tokens=output_tokens)


class FakeLLM:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def __call__(self, system_prompt, user_message, output_model, **kwargs):
        self.calls.append(user_message)
        item = self.results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def state():
    return {"job_id": "j", "raw_text": "ACME statement text", "llm_calls": []}


def test_valid_output_is_normalised_and_usage_recorded(monkeypatch, state):
    fake = FakeLLM(result(GOOD))
    monkeypatch.setattr(nodes, "extract_structured", fake)
    out = node_extract_fields(state)
    assert not out.get("error")
    assert out["validated_data"]["currency"] == "USD"
    assert out["llm_calls"] == [{"attempt": 1, "model": "fake", "input_tokens": 100, "output_tokens": 50, "stop_reason": "end_turn"}]
    assert node_finalize(out)["statement_month"] == "2026-08"


def test_truncated_output_fails_loudly_and_is_not_retried(monkeypatch, state):
    fake = FakeLLM(result('{"account_holder": "Jane', stop_reason="max_tokens", output_tokens=16384))
    monkeypatch.setattr(nodes, "extract_structured", fake)
    out = node_extract_fields(state)
    assert out["error_code"] == ErrorCode.TRUNCATED_OUTPUT
    assert len(fake.calls) == 1
    assert "validated_data" not in out


def test_refusal_is_its_own_error_code(monkeypatch, state):
    monkeypatch.setattr(nodes, "extract_structured", FakeLLM(result("", stop_reason="refusal")))
    assert node_extract_fields(state)["error_code"] == ErrorCode.MODEL_REFUSED


def test_validation_failure_retries_with_the_error_and_the_source_text(monkeypatch, state):
    bad = {**GOOD, "statement_date": "03/04/2026"}   # ambiguous, rejected by the validator
    fake = FakeLLM(result(bad), result(GOOD))
    monkeypatch.setattr(nodes, "extract_structured", fake)
    out = node_extract_fields(state)
    assert not out.get("error")
    assert len(fake.calls) == 2
    assert "ACME statement text" in fake.calls[1]          # retry sees the document
    assert "statement_date" in fake.calls[1]               # and the validation error
    assert "ISO 8601" in fake.calls[1]
    assert len(out["llm_calls"]) == 2


def test_second_validation_failure_is_schema_invalid(monkeypatch, state):
    bad = {**GOOD, "currency": "dollars"}
    fake = FakeLLM(result(bad), result(bad))
    monkeypatch.setattr(nodes, "extract_structured", fake)
    out = node_extract_fields(state)
    assert out["error_code"] == ErrorCode.SCHEMA_INVALID
    assert "currency" in out["error"]
    assert len(fake.calls) == 2


def test_api_error_after_sdk_retries_is_api_error(monkeypatch, state):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(529, request=request)
    err = anthropic.APIStatusError("overloaded", response=response, body=None)
    monkeypatch.setattr(nodes, "extract_structured", FakeLLM(err))
    out = node_extract_fields(state)
    assert out["error_code"] == ErrorCode.API_ERROR


def test_model_node_is_skipped_after_an_upstream_error(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(nodes, "extract_structured", fake)
    state = {"error": "Scanned PDFs not supported yet", "error_code": "SCANNED"}
    assert node_extract_fields(state) == state
    assert fake.calls == []


def test_input_cap_is_enforced_before_any_model_call(monkeypatch, tmp_path):
    from agents.statement_extraction.nodes import node_extract_text
    monkeypatch.setattr(nodes, "MAX_INPUT_CHARS", 10)
    monkeypatch.setattr(nodes.pdfplumber, "open", lambda p: FakePdf("x" * 50))
    out = node_extract_text({"job_id": "j", "file_path": "whatever.pdf"})
    assert out["error_code"] == ErrorCode.INPUT_TOO_LARGE


class FakePage:
    def __init__(self, text):
        self._text = text

    def extract_text(self):
        return self._text


class FakePdf:
    def __init__(self, text):
        self.pages = [FakePage(text)]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.mark.parametrize("raw,expected", [
    ("2026-08-31", "2026-08-31"),
    ("31 Aug 2026", "2026-08-31"),
    ("31 August 2026", "2026-08-31"),
    ("Aug 31, 2026", "2026-08-31"),
    (None, None),
])
def test_dates_normalise_to_iso(raw, expected):
    assert normalise_date(raw) == expected


@pytest.mark.parametrize("raw", ["03/04/2026", "04.03.2026", "31-31-2025", "yesterday"])
def test_ambiguous_or_bad_dates_are_rejected(raw):
    with pytest.raises(ValueError):
        normalise_date(raw)


def test_statement_data_rejects_bad_transaction_date():
    with pytest.raises(Exception):
        StatementData(**{**GOOD, "transactions": [{"date": "31-31-2025", "description": "x", "amount": 1}]})
