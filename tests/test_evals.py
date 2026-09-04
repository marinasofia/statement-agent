import json

import pytest

from core.cassettes import CassetteStore, CassetteMissing
from core.llm import LLMResult
from evals.run_evals import score_case


def test_cassette_roundtrip_and_key_changes_with_prompt(tmp_path):
    store = CassetteStore(str(tmp_path), "record")
    entry = LLMResult(text='{"a": 1}', stop_reason="end_turn", model="m", input_tokens=3, output_tokens=2, latency_ms=40).to_cassette()
    store.save("m", "sys", "user", {"type": "object"}, entry)
    replay = CassetteStore(str(tmp_path), "replay")
    loaded = LLMResult.from_cassette(replay.load("m", "sys", "user", {"type": "object"}))
    assert loaded.text == '{"a": 1}' and loaded.latency_ms == 40
    with pytest.raises(CassetteMissing):
        replay.load("m", "sys changed", "user", {"type": "object"})


def test_cassette_store_is_off_without_both_env_vars(monkeypatch):
    monkeypatch.delenv("LLM_CASSETTE_MODE", raising=False)
    monkeypatch.delenv("LLM_CASSETTE_DIR", raising=False)
    assert CassetteStore.from_env() is None
    monkeypatch.setenv("LLM_CASSETTE_MODE", "replay")
    assert CassetteStore.from_env() is None


EXPECTED = {
    "expect_status": "OK", "expect_error_code": None, "account_holder": "Alex Morgan",
    "account_number": "4401 2299 0031", "currency": "USD", "opening_balance": 1250.0,
    "closing_balance": 3899.0, "transaction_count": 2, "transactions_sum": 2649.0, "statement_date": "2026-08-31",
}
GOOD_STATE = {
    "status": "OK", "llm_calls": [{}],
    "validated_data": {"account_holder": "ALEX  MORGAN", "account_number": "440122990031", "currency": "USD",
                       "opening_balance": 1250.0, "closing_balance": 3899.004, "statement_date": "2026-08-31",
                       "transactions": [{"amount": 2700.0}, {"amount": -51.0}]},
}


def test_scoring_folds_case_whitespace_and_account_formatting():
    checks = score_case(EXPECTED, GOOD_STATE)
    assert all(checks.values()), checks


def test_scoring_catches_a_wrong_balance_and_a_missing_row():
    bad = json.loads(json.dumps(GOOD_STATE))
    bad["validated_data"]["closing_balance"] = 3900.0
    bad["validated_data"]["transactions"].pop()
    checks = score_case(EXPECTED, bad)
    assert checks["closing_balance"] is False
    assert checks["transaction_count"] is False and checks["transactions_sum"] is False
    assert checks["account_holder"] is True


def test_scoring_of_a_deterministic_rejection_requires_no_model_call():
    expected = {"expect_status": "FAILED", "expect_error_code": "SCANNED"}
    assert score_case(expected, {"error": "x", "error_code": "SCANNED", "llm_calls": []}) == {"error_code": True, "no_model_call": True}
    assert score_case(expected, {"error": "x", "error_code": "SCANNED", "llm_calls": [{}]})["no_model_call"] is False
