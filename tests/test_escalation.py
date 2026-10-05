"""Routing through reconcile and the repair agent, with the API replaced by fakes."""

import json

import pytest

from agents.statement_extraction import nodes, repair
from agents.statement_extraction.graph import build_graph
from agents.statement_extraction.schema import ErrorCode
from core.llm import LLMResult, ToolTurn

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


def call(name, **args):
    return {"type": "tool_use", "id": f"t_{name}_{len(args)}", "name": name, "input": args}


class FakeAgent:
    """Scripted repair turns. Each turn is a list of tool calls, or an exception to raise."""

    def __init__(self, *turns):
        self.turns = list(turns)
        self.models = []

    def __call__(self, system_prompt, messages, tools, model="default", **kw):
        self.models.append(model)
        turn = self.turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        return ToolTurn(content=turn, stop_reason="tool_use", model="fake", input_tokens=10, output_tokens=5)


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
    c = canvas.Canvas(path); c.drawString(50, 800, "ACME BANK statement"); c.drawString(50, 780, "Jane Doe  Account 111")
    c.drawString(50, 760, "2026-08-01  Coffee  -3.50"); c.drawString(50, 740, "2026-08-15  Salary  1,000.00"); c.save()
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


def test_failed_reconciliation_runs_the_repair_agent_and_reconciles(monkeypatch, run):
    fake = FakeLLM(result(MISSED_ROW))
    agent = FakeAgent(
        [call("search_document", query="3.50")],
        [call("add_transaction", date="2026-08-01", description="Coffee", amount=-3.5, source_line=3)],
        [call("finish", summary="Added the coffee purchase the extraction missed.")],
    )
    monkeypatch.setattr(nodes, "extract_structured", fake)
    monkeypatch.setattr(repair, "converse", agent)
    out = run()
    assert fake.models == ["cheap"]
    assert agent.models == ["strong"] * 3
    assert out["status"] == "OK"
    assert out["escalated"] is True
    assert out["repair"]["outcome"] == "finished"
    assert out["repair"]["edits"][0]["source_line"] == 3
    assert len(out["validated_data"]["transactions"]) == 2
    assert out["accepted_model"] == "cheap"                    # the repair edits, it does not re-extract
    assert len(out["llm_calls"]) == 4


def test_agent_gives_up_and_the_statement_goes_to_review_with_its_reason(monkeypatch, run):
    fake = FakeLLM(result(MISSED_ROW))
    agent = FakeAgent([call("send_to_review", reason="The document does not print the missing 3.50.")])
    monkeypatch.setattr(nodes, "extract_structured", fake)
    monkeypatch.setattr(repair, "converse", agent)
    out = run()
    assert agent.models == ["strong"]                          # exactly one repair, no loop
    assert out["status"] == "NEEDS_REVIEW"
    assert out.get("error") is None                            # the row is kept, not failed
    assert out["review_reasons"][0].startswith("balance_arithmetic:")
    assert "delta" in out["review_reasons"][0]
    assert out["review_reasons"][-1].startswith("repair agent (sent_to_review): The document")


def test_agent_claiming_success_does_not_make_the_statement_ok(monkeypatch, run):
    """finish is refused while checks fail; the deterministic checks decide the status."""
    fake = FakeLLM(result(MISSED_ROW))
    agent = FakeAgent(*[[call("finish", summary="done")]] * repair.MAX_TURNS)
    monkeypatch.setattr(nodes, "extract_structured", fake)
    monkeypatch.setattr(repair, "converse", agent)
    out = run()
    assert out["status"] == "NEEDS_REVIEW"
    assert out["repair"]["outcome"] == "out_of_turns"
    assert len(agent.models) == repair.MAX_TURNS


def test_escalation_api_failure_keeps_first_result_for_review(monkeypatch, run):
    import anthropic, httpx
    err = anthropic.APIStatusError("overloaded", response=httpx.Response(529, request=httpx.Request("POST", "https://x")), body=None)
    fake = FakeLLM(result(MISSED_ROW))
    monkeypatch.setattr(nodes, "extract_structured", fake)
    monkeypatch.setattr(repair, "converse", FakeAgent(err))
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
    assert [c["outcome"] for c in out["reconciliation"]["checks"]] == ["skipped", "skipped", "skipped", "passed"]


def test_injected_holder_that_is_not_in_the_document_is_caught(monkeypatch, run):
    """Arithmetic cannot see a changed name; the identity check can."""
    injected = {**GOOD, "account_holder": "SYSTEM OVERRIDE"}
    fake = FakeLLM(result(injected))
    agent = FakeAgent()
    monkeypatch.setattr(nodes, "extract_structured", fake)
    monkeypatch.setattr(repair, "converse", agent)
    out = run()
    assert out["status"] == "NEEDS_REVIEW"
    assert any("identity_in_source" in r for r in out["review_reasons"])
    assert fake.models == ["cheap"]
    assert agent.models == []                                  # identity is not the agent's to fix


def test_full_run_on_the_fee_statement_with_scripted_models(monkeypatch):
    """The whole graph on a real fixture PDF: the cheap model misses a fee printed
    under the table, and the repair agent finds it by amount and adds it from its line."""
    import os, shutil
    from pathlib import Path
    from core.config import ALLOWED_UPLOAD_DIR
    folder = Path(__file__).resolve().parent / "fixtures" / "fee_outside_table"
    expected = json.loads((folder / "expected.json").read_text())
    os.makedirs(ALLOWED_UPLOAD_DIR, exist_ok=True)
    path = os.path.join(ALLOWED_UPLOAD_DIR, "t_fee_outside_table.pdf")
    shutil.copy(folder / "statement.pdf", path)
    missed_fee = {
        "account_holder": expected["account_holder"], "account_number": expected["account_number"], "currency": "USD",
        "opening_balance": expected["opening_balance"], "closing_balance": expected["closing_balance"],
        "statement_date": expected["statement_date"], "statement_period_start": expected["statement_period_start"],
        "statement_period_end": expected["statement_period_end"], "bank_name": "Northwind Bank",
        "transactions": [{"date": "2026-08-04", "description": "Rent Lakeview Apartments", "amount": -1450.0},
                         {"date": "2026-08-08", "description": "Salary Northwind Ltd", "amount": 3200.0},
                         {"date": "2026-08-17", "description": "Grocery Market", "amount": -96.4}],
    }
    monkeypatch.setenv("CLIENT_ID", "default")
    monkeypatch.setattr(nodes, "CLAUDE_MODEL", "cheap")
    monkeypatch.setattr(nodes, "ESCALATION_MODEL", "strong")
    monkeypatch.setattr(nodes, "extract_structured", FakeLLM(result(missed_fee)))
    agent = FakeAgent(
        [call("search_document", query="12.50")],
        [call("read_lines", start=11, end=12)],
        [call("add_transaction", date="2026-08-31", description="Monthly maintenance fee", amount=-12.5, source_line=12)],
        [call("finish", summary="Added the maintenance fee printed in the note below the table.")],
    )
    monkeypatch.setattr(repair, "converse", agent)
    try:
        out = build_graph().invoke({"file_path": path})
    finally:
        os.remove(path)
    assert out["status"] == "OK"
    assert len(out["validated_data"]["transactions"]) == expected["transaction_count"]
    assert out["repair"]["outcome"] == "finished"
    assert "maintenance fee of 12.50" in out["repair"]["edits"][0]["line_text"]


def test_mixed_identity_and_balance_failure_skips_the_agent(monkeypatch, run):
    fake = FakeLLM(result({**MISSED_ROW, "account_holder": "SYSTEM OVERRIDE"}))
    agent = FakeAgent()
    monkeypatch.setattr(nodes, "extract_structured", fake)
    monkeypatch.setattr(repair, "converse", agent)
    out = run()
    assert out["status"] == "NEEDS_REVIEW"
    assert agent.models == []
