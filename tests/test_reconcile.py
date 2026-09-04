import pytest

from agents.statement_extraction.reconcile import reconcile, BALANCE_TOLERANCE

BASE = {
    "opening_balance": 100.00,
    "closing_balance": 1096.50,
    "statement_period_start": "2026-08-01",
    "statement_period_end": "2026-08-31",
    "transactions": [
        {"date": "2026-08-01", "description": "Coffee", "amount": -3.50},
        {"date": "2026-08-15", "description": "Salary", "amount": 1000.00},
    ],
}


def test_balanced_statement_passes_all_checks():
    r = reconcile(BASE)
    assert r.ok
    assert r.balance_delta == 0.0
    assert [c.outcome for c in r.checks] == ["passed", "passed", "passed"]


def test_half_a_cent_of_rounding_is_tolerated():
    r = reconcile({**BASE, "closing_balance": 1096.505})
    assert r.ok
    assert abs(r.balance_delta) <= BALANCE_TOLERANCE


def test_one_missing_transaction_fails_with_the_delta():
    r = reconcile({**BASE, "closing_balance": 1108.50})   # a 12.00 credit was missed
    assert not r.ok
    assert r.balance_delta == -12.0
    assert r.reasons == [
        "balance_arithmetic: opening 100.00 + transactions 996.50 = 1096.50, closing is 1108.50 (delta -12.00)"
    ]


def test_missing_opening_balance_skips_rather_than_fails():
    r = reconcile({**BASE, "opening_balance": None})
    assert r.ok
    assert r.checks[0].outcome == "skipped"
    assert r.balance_delta is None


def test_transaction_outside_the_period_fails():
    txs = BASE["transactions"] + [{"date": "2026-09-02", "description": "Late", "amount": 0.0}]
    r = reconcile({**BASE, "transactions": txs})
    assert not r.ok
    assert r.reasons == ["dates_in_period: 1 of 3 transactions fall outside 2026-08-01 to 2026-08-31"]


def test_inverted_period_fails():
    r = reconcile({**BASE, "statement_period_start": "2026-08-31", "statement_period_end": "2026-08-01"})
    assert any(c.name == "period_ordered" and c.outcome == "failed" for c in r.checks)


def test_no_transactions_skips_arithmetic():
    r = reconcile({**BASE, "transactions": None})
    assert r.ok
    assert r.checks[0].outcome == "skipped"


def test_sign_error_is_caught_by_arithmetic():
    # The model dropped the minus on the debit.
    txs = [{**BASE["transactions"][0], "amount": 3.50}, BASE["transactions"][1]]
    r = reconcile({**BASE, "transactions": txs})
    assert not r.ok
    assert r.balance_delta == 7.0
