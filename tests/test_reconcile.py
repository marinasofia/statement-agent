import pytest

from agents.statement_extraction.reconcile import reconcile

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
    r = reconcile({**BASE, "account_holder": "Jane Doe", "account_number": "111"}, "JANE DOE\nAccount: 111")
    assert r.ok
    assert r.balance_delta == 0.0
    assert [c.outcome for c in r.checks] == ["passed", "passed", "passed", "passed"]


def test_holder_or_account_not_in_the_document_fails():
    data = {**BASE, "account_holder": "SYSTEM OVERRIDE", "account_number": "111"}
    r = reconcile(data, "Statement for Jane Doe, account 0000 111")
    assert not r.ok
    assert r.reasons[-1] == "identity_in_source: account holder not found in the document text"


def test_masked_and_spaced_account_numbers_still_match():
    data = {**BASE, "account_holder": "jane   doe", "account_number": "**** 4401"}
    assert reconcile(data, "Jane Doe\nAccount ending 44 01").checks[-1].outcome == "passed"


def test_identity_check_skips_without_document_text():
    assert reconcile({**BASE, "account_holder": "Jane Doe"}).checks[-1].outcome == "skipped"


def test_float_noise_never_fails_a_balanced_statement():
    # 0.1 + 0.2 is 0.30000000000000004 in binary floating point; exact decimals make it 0.30.
    r = reconcile({**BASE, "opening_balance": 0.1, "closing_balance": 0.3,
                   "transactions": [{"date": "2026-08-02", "description": "x", "amount": 0.2}]})
    assert r.ok and r.balance_delta == 0.0


def test_one_cent_off_fails():
    r = reconcile({**BASE, "closing_balance": 1096.51})
    assert not r.ok
    assert r.balance_delta == -0.01
    assert r.reasons == [
        "balance_arithmetic: opening 100.00 + transactions 996.50 = 1096.50, closing is 1096.51 (delta -0.01)"
    ]


def test_sub_cent_amounts_are_not_rounded_away():
    r = reconcile({**BASE, "closing_balance": 1096.505})
    assert not r.ok


def test_currency_minor_unit_sets_precision():
    yen = {"opening_balance": 1000, "closing_balance": 4000, "currency": "JPY",
           "transactions": [{"date": None, "description": "Pay", "amount": 3000}]}
    assert reconcile(yen).checks[0].detail == "opening 1000 + transactions 3000 = closing 4000"
    dinar = {**yen, "currency": "KWD", "opening_balance": 1.25, "closing_balance": 1.255,
             "transactions": [{"date": None, "description": "Fee", "amount": 0.005}]}
    assert reconcile(dinar).checks[0].detail == "opening 1.250 + transactions 0.005 = closing 1.255"


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
