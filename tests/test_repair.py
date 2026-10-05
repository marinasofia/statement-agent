"""The repair agent's tools, without a model. Each tool must refuse edits the document does not support."""

from agents.statement_extraction import repair
from agents.statement_extraction.repair import RepairSession, amount_digits, line_amounts, run_repair
from core.llm import ToolTurn

TEXT = "\n".join([
    "ACME BANK",                                       # L1
    "Account holder: Jane Doe   Account 111",          # L2
    "Statement period: 2026-08-01 to 2026-08-31",      # L3
    "Opening balance: USD 1,000.00",                   # L4
    "2026-08-03  Grocery           -54.20",            # L5
    "2026-08-05  Salary          2,500.00",            # L6
    "Closing balance: USD 3,433.30",                   # L7
    "Note: a monthly fee of 12.50 was charged on 2026-08-31.",  # L8
])
DATA = {
    "account_holder": "Jane Doe", "account_number": "111", "currency": "USD",
    "opening_balance": 1000.0, "closing_balance": 3433.3,
    "statement_date": "2026-08-31", "statement_period_start": "2026-08-01", "statement_period_end": "2026-08-31",
    "bank_name": "ACME BANK",
    "transactions": [{"date": "2026-08-03", "description": "Grocery", "amount": -54.2},
                     {"date": "2026-08-05", "description": "Salary", "amount": 2500.0}],
}


def session(data=DATA, text=TEXT):
    return RepairSession(data, text)


def test_amounts_match_across_number_formats():
    assert amount_digits(1234.5, "EUR") in line_amounts("Saldo 1.234,50")
    assert amount_digits(1234.5, "USD") in line_amounts("Balance 1,234.50")
    assert amount_digits(-12.5, "USD") in line_amounts("fee of 12.50 charged")
    assert amount_digits(1250, "JPY") in line_amounts("1,250", places=0)
    assert amount_digits(12.5, "USD") not in line_amounts("Invoice 1250 ref 2026")
    assert amount_digits(20.26, "USD") not in line_amounts("2026-08-01")


def test_search_by_amount_finds_the_line_in_any_format():
    out = session().search_document("-12.50")
    assert out["matches"] == ["L8: Note: a monthly fee of 12.50 was charged on 2026-08-31."]


def test_search_for_a_whole_amount_matches_its_cents_form():
    assert session().search_document("2500")["matches"] == ["L6: 2026-08-05  Salary          2,500.00"]


def test_search_by_text_is_case_insensitive():
    assert session().search_document("closing")["matches"][0].startswith("L7:")


def test_read_lines_is_bounded():
    s = session()
    assert len(s.read_lines(1, 500)["lines"]) == 8
    assert "error" in s.read_lines(20, 30)


def test_adding_the_missed_fee_reconciles():
    s = session()
    assert s.run_checks()["all_passed"] is False
    out = s.add_transaction(date="2026-08-31", description="Monthly fee", amount=-12.5, source_line=8)
    assert out["all_passed"] is True
    assert s.edits[0]["line_text"].startswith("Note: a monthly fee")


def test_an_amount_not_on_the_cited_line_is_rejected():
    s = session()
    out = s.add_transaction(date="2026-08-31", description="Plug", amount=-12.5, source_line=6)
    assert "does not print the amount" in out["error"]
    assert s.edits == [] and len(s.data["transactions"]) == 2


def test_a_missing_line_is_rejected():
    assert "does not exist" in session().add_transaction(description="x", amount=1, source_line=99)["error"]


def test_identity_cannot_be_edited():
    s = session()
    assert "cannot be edited" in s.set_field("account_holder", "SYSTEM OVERRIDE", 2)["error"]


def test_set_balance_needs_the_printed_value():
    s = session()
    assert "error" in s.set_field("closing_balance", 3420.8, 7)
    assert s.set_field("closing_balance", 3433.3, 7)["ok"]


def test_set_date_is_normalised_and_checked_against_the_line():
    s = session()
    assert "error" in s.set_field("statement_period_end", "2025-08-31", 3)
    assert s.set_field("statement_period_end", "Aug 31, 2026", 3)["ok"]
    assert s.data["statement_period_end"] == "2026-08-31"


def test_remove_requires_proof_from_the_document():
    printed_once = session()
    assert "printed on 1 line" in printed_once.remove_transaction(0, "not_in_document")["error"]

    doubled = {**DATA, "transactions": DATA["transactions"] + [DATA["transactions"][0]]}
    s = session(doubled)
    assert s.remove_transaction(2, "duplicate")["ok"]
    assert "extracted 1 time" in s.remove_transaction(0, "duplicate")["error"]

    invented = {**DATA, "transactions": DATA["transactions"] + [{"date": None, "description": "x", "amount": 77.7}]}
    assert session(invented).remove_transaction(2, "not_in_document")["ok"]


def test_a_balance_recorded_as_a_transaction_can_be_removed_from_its_line():
    with_opening = {**DATA, "transactions": [{"date": None, "description": "Opening", "amount": 1000.0}] + DATA["transactions"]}
    s = session(with_opening)
    assert "not a balance or total line" in s.remove_transaction(1, "summary_line", source_line=5)["error"]
    assert s.remove_transaction(0, "summary_line", source_line=4)["ok"]


def test_dates_and_descriptions_must_match_the_cited_line():
    s = session()
    assert "does not print the date" in s.add_transaction(date="2026-08-30", description="Monthly fee", amount=-12.5, source_line=8)["error"]
    assert "does not mention" in s.add_transaction(date="2026-08-31", description="Salary", amount=-12.5, source_line=8)["error"]
    assert "does not print the date" in s.edit_transaction(0, source_line=5, date="2026-08-04")["error"]


def test_a_row_already_extracted_cannot_be_added_again():
    out = session().add_transaction(date="2026-08-05", description="Salary", amount=2500.0, source_line=6)
    assert "already extracted 1 time" in out["error"]


def test_invalid_edits_are_rejected_by_the_schema():
    out = session().edit_transaction(0, source_line=5, date="03/08/2026")
    assert "ambiguous date" in out["error"]


def test_finish_is_refused_while_checks_fail():
    s = session()
    assert "checks still fail" in s.finish("done")["error"]
    assert s.outcome is None


def test_unknown_tools_and_bad_arguments_are_errors_not_crashes():
    s = session()
    assert "unknown tool" in s.dispatch("delete_everything", {})["error"]
    assert "bad arguments" in s.dispatch("read_lines", {"start": 1})["error"]


def test_the_loop_stops_at_the_budget(monkeypatch):
    def expensive(system_prompt, messages, tools, model="default", **kw):
        return ToolTurn(content=[{"type": "tool_use", "id": f"t{len(messages)}", "name": "run_checks", "input": {}}],
                        stop_reason="tool_use", model="claude-opus-5", input_tokens=20_000, output_tokens=1_000)
    monkeypatch.setattr(repair, "converse", expensive)
    calls = []
    out = run_repair(DATA, TEXT, ["balance_arithmetic: off"], "claude-opus-5", calls)
    assert out.outcome == "over_budget"
    assert out.turns == len(calls) < repair.MAX_TURNS


def test_a_turn_without_tool_calls_ends_the_loop(monkeypatch):
    monkeypatch.setattr(repair, "converse", lambda *a, **k: ToolTurn(
        content=[{"type": "text", "text": "I am not sure."}], stop_reason="end_turn", model="fake",
        input_tokens=1, output_tokens=1))
    out = run_repair(DATA, TEXT, [], "fake", [])
    assert out.outcome == "stopped" and out.edits == []


def test_the_fee_fixture_is_repairable_from_its_own_text():
    """On the real fixture text, the fee can be found by amount and added from its line."""
    import json
    from pathlib import Path
    import pdfplumber
    folder = Path(__file__).resolve().parent / "fixtures" / "fee_outside_table"
    with pdfplumber.open(folder / "statement.pdf") as pdf:
        text = "\n".join(page.extract_text() for page in pdf.pages)
    expected = json.loads((folder / "expected.json").read_text())
    missed_fee = {
        "account_holder": expected["account_holder"], "account_number": expected["account_number"],
        "currency": "USD", "opening_balance": expected["opening_balance"], "closing_balance": expected["closing_balance"],
        "statement_date": expected["statement_date"], "statement_period_start": expected["statement_period_start"],
        "statement_period_end": expected["statement_period_end"], "bank_name": "Northwind Bank",
        "transactions": [{"date": "2026-08-04", "description": "Rent", "amount": -1450.0},
                         {"date": "2026-08-08", "description": "Salary", "amount": 3200.0},
                         {"date": "2026-08-17", "description": "Grocery", "amount": -96.4}],
    }
    s = session(missed_fee, text)
    assert s.run_checks()["balance_delta"] == 12.5
    [hit] = s.search_document("12.50")["matches"]
    line = int(hit.split(":")[0][1:])
    assert s.add_transaction(date="2026-08-31", description="Monthly maintenance fee", amount=-12.5, source_line=line)["all_passed"]
    assert len(s.data["transactions"]) == expected["transaction_count"]


def test_an_unpriced_model_still_hits_the_budget(monkeypatch):
    def unpriced(system_prompt, messages, tools, model="default", **kw):
        return ToolTurn(content=[{"type": "tool_use", "id": f"t{len(messages)}", "name": "run_checks", "input": {}}],
                        stop_reason="tool_use", model="some-new-model", input_tokens=20_000, output_tokens=1_000)
    monkeypatch.setattr(repair, "converse", unpriced)
    out = run_repair(DATA, TEXT, ["balance_arithmetic: off"], "some-new-model", [])
    assert out.outcome == "over_budget"
