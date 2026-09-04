"""Routing through reconcile and escalate, with the API replaced by a fake."""

import json

import pytest

from agents.statement_extraction import nodes
from agents.statement_extraction.graph import build_graph
from agents.statement_extraction.schema import ErrorCode
from core.llm import LLMResult

GOOD = {
    "account_holder": "Jane Doe", "closing_balance": 1096.5, "opening_balance": 100.0,
    "account_number": "111", "statement_date": "2026-08-31",
    "statement_period_start": "2026-08-01", "statement_period_end": "2026-08-31",
    "currency": "USD", "bank_name": "ACME",
    "transactions": [{"date": "2026-08-01", "description": "Coffee", "amount": -3.5},
                     {"date": "2026-08-15", "description": "Salary", "amount": 1000.0}],
}
MISSED_ROW = {**GOOD, "transactions": GOOD["transactions"][1:]}   # off by 3.50


def result(payload, stop_reason="end_turn"):
    return LLMResult(text=json.dumps(payload), stop_reason=stop_reason, model="fake", input_tokens=10, output_tokens=5)


class FakeLLM:
    def __init__(self, *results):
        self.results = list(results)
        self.models = []

    def __call__(self, system_prompt, user_message, output_model, model="default", **kw):
        self.models.append(model)
        item = self.results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def run(monkeypatch, tmp_path):
    """Run the compiled graph on a real (tiny) PDF inside the upload dir."""
    import os
    from reportlab.pdfgen import canvas
    from core.config import ALLOWED_UPLOAD_DIR
    monkeypatch.setenv("CLIENT_ID", "default")
    monkeypatch.setattr(nodes, "CLAUDE_MODEL", "cheap")
    monkeypatch.setattr(nodes, "ESCALATION_MODEL", "strong")
    os.makedirs(ALLOWED_UPLOAD_DIR, exist_ok=True)
    path = os.path.join(ALLOWED_UPLOAD_DIR, "t_escalation.pdf")
    c = canvas.Canvas(path); c.drawString(50, 800, "ACME BANK statement"); c.save()
    graph = build_graph()
    yield lambda: graph.invoke({"file_path": path})
    os.remove(path)


def test_reconciled_first_time_does_not_escalate(monkeypatch, run):
    fake = FakeLLM(result(GOOD))
    monkeypatch.setattr(nodes, "extract_structured", fake)
    out = run()
    assert out["status"] == "OK"
    assert out["escalated"] is False
    assert fake.models == ["cheap"]
    assert out["reconciliation"]["balance_delta"] == 0.0


def test_failed_reconciliation_escalates_once_and_accepts_the_stronger_result(monkeypatch, run):
    fake = FakeLLM(result(MISSED_ROW), result(GOOD))
    monkeypatch.setattr(nodes, "extract_structured", fake)
    out = run()
    assert fake.models == ["cheap", "strong"]
    assert out["status"] == "OK"
    assert out["escalated"] is True
    assert len(out["validated_data"]["transactions"]) == 2
    assert [c["model"] for c in out["llm_calls"]] == ["fake", "fake"] and len(out["llm_calls"]) == 2


def test_still_failing_after_escalation_is_needs_review_with_reasons(monkeypatch, run):
    fake = FakeLLM(result(MISSED_ROW), result(MISSED_ROW))
    monkeypatch.setattr(nodes, "extract_structured", fake)
    out = run()
    assert fake.models == ["cheap", "strong"]          # exactly one escalation, no loop
    assert out["status"] == "NEEDS_REVIEW"
    assert out.get("error") is None                    # the row is kept, not failed
    assert out["review_reasons"][0].startswith("balance_arithmetic:")
    assert "delta" in out["review_reasons"][0]


def test_escalation_api_failure_keeps_first_result_for_review(monkeypatch, run):
    import anthropic, httpx
    err = anthropic.APIStatusError("overloaded", response=httpx.Response(529, request=httpx.Request("POST", "https://x")), body=None)
    fake = FakeLLM(result(MISSED_ROW), err)
    monkeypatch.setattr(nodes, "extract_structured", fake)
    out = run()
    assert out["status"] == "NEEDS_REVIEW"
    assert out["validated_data"]["closing_balance"] == 1096.5
    assert any(r.startswith("escalation: API_ERROR") for r in out["review_reasons"])


def test_escalation_can_be_disabled(monkeypatch, run):
    monkeypatch.setattr(nodes, "ESCALATION_MODEL", "")
    fake = FakeLLM(result(MISSED_ROW))
    monkeypatch.setattr(nodes, "extract_structured", fake)
    out = run()
    assert fake.models == ["cheap"]
    assert out["status"] == "NEEDS_REVIEW"


def test_skipped_checks_do_not_send_a_statement_to_review(monkeypatch, run):
    no_opening = {**GOOD, "opening_balance": None, "statement_period_start": None, "statement_period_end": None}
    fake = FakeLLM(result(no_opening))
    monkeypatch.setattr(nodes, "extract_structured", fake)
    out = run()
    assert out["status"] == "OK"
    assert [c["outcome"] for c in out["reconciliation"]["checks"]] == ["skipped", "skipped", "skipped"]
