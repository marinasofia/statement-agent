"""Deterministic checks on what the model returned.

Nothing in this module calls a model. The checks answer one question: do
the numbers the model read agree with each other? A statement whose
opening balance plus its transactions does not land on its closing
balance has either been misread or is missing rows, and either way it
must not go quietly into the main table.

Each check has three outcomes: passed, failed, or skipped because the
fields it needs were not present. Skipped is not a failure; a statement
without an opening balance cannot be reconciled, and the review sheet
says so rather than pretending it was checked.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

# Digits after the decimal point in each currency's smallest unit (ISO 4217). Everything else uses 2.
MINOR_UNITS = {
    "JPY": 0, "KRW": 0, "VND": 0, "CLP": 0, "ISK": 0, "UGX": 0,
    "BHD": 3, "KWD": 3, "OMR": 3, "JOD": 3, "TND": 3, "IQD": 3, "LYD": 3,
}


def minor_unit(currency: Optional[str]) -> int:
    return MINOR_UNITS.get((currency or "").upper(), 2)


def to_money(value) -> Decimal:
    """Exact decimal for a number that arrived as JSON.

    Decimal(str(x)) uses Python's shortest round-trip form, so 110.01 becomes
    Decimal("110.01") rather than the binary expansion 110.0100000000000051..."""
    return Decimal(str(value))


@dataclass
class Check:
    name: str
    outcome: str            # "passed", "failed", "skipped"
    detail: str = ""


@dataclass
class ReconciliationResult:
    checks: list = field(default_factory=list)
    balance_delta: Optional[float] = None

    @property
    def ok(self) -> bool:
        return all(c.outcome != "failed" for c in self.checks)

    @property
    def reasons(self) -> list[str]:
        return [f"{c.name}: {c.detail}" for c in self.checks if c.outcome == "failed"]

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "balance_delta": self.balance_delta,
            "checks": [{"name": c.name, "outcome": c.outcome, "detail": c.detail} for c in self.checks],
        }


def check_balance_arithmetic(data: dict) -> tuple[Check, Optional[float]]:
    opening = data.get("opening_balance")
    closing = data.get("closing_balance")
    transactions = data.get("transactions")
    if opening is None or closing is None or not transactions:
        return Check("balance_arithmetic", "skipped", "needs opening balance and transactions"), None

    # Exact arithmetic in the currency's minor unit: bank amounts are whole cents
    # (or yen, or fils), so any difference at all is a misread or a missing row.
    places = minor_unit(data.get("currency"))
    o, c = to_money(opening), to_money(closing)
    total = sum((to_money(t.get("amount") or 0) for t in transactions), Decimal(0))
    delta = o + total - c
    fmt = lambda d: f"{d:.{places}f}"
    if delta == 0:
        return Check("balance_arithmetic", "passed", f"opening {fmt(o)} + transactions {fmt(total)} = closing {fmt(c)}"), 0.0
    return Check(
        "balance_arithmetic", "failed",
        f"opening {fmt(o)} + transactions {fmt(total)} = {fmt(o + total)}, closing is {fmt(c)} (delta {delta:+.{places}f})",
    ), float(delta)


def check_dates_in_period(data: dict) -> Check:
    start = data.get("statement_period_start")
    end = data.get("statement_period_end")
    transactions = data.get("transactions") or []
    dated = [t["date"] for t in transactions if t.get("date")]
    if not start or not end or not dated:
        return Check("dates_in_period", "skipped", "needs a statement period and dated transactions")
    # Dates are ISO strings after validation, so string comparison is date order.
    outside = [d for d in dated if d < start or d > end]
    if not outside:
        return Check("dates_in_period", "passed", f"{len(dated)} transactions between {start} and {end}")
    return Check("dates_in_period", "failed", f"{len(outside)} of {len(dated)} transactions fall outside {start} to {end}")


def check_period_is_ordered(data: dict) -> Check:
    start = data.get("statement_period_start")
    end = data.get("statement_period_end")
    if not start or not end:
        return Check("period_ordered", "skipped", "needs both period dates")
    if start <= end:
        return Check("period_ordered", "passed", f"{start} to {end}")
    return Check("period_ordered", "failed", f"period starts {start} after it ends {end}")


def _fold_text(value) -> str:
    return " ".join(str(value or "").casefold().split())


def check_identity_in_source(data: dict, source_text: Optional[str]) -> Check:
    """The holder and account number must be printed in the document itself.

    Arithmetic catches a wrong number, but nothing else catches a wrong name or
    account: an injected instruction or a hallucination that only changes them
    would pass every other check. The account number is compared on digits so
    spacing and masking ("**** 1234") do not matter."""
    holder, number = data.get("account_holder"), data.get("account_number")
    if not source_text or not (holder or number):
        return Check("identity_in_source", "skipped", "needs the document text and a holder or account number")
    missing = []
    if holder and _fold_text(holder) not in _fold_text(source_text):
        missing.append("account holder")
    digits = "".join(ch for ch in str(number or "") if ch.isdigit())
    if digits and digits not in "".join(ch for ch in source_text if ch.isdigit()):
        missing.append("account number")
    if missing:
        return Check("identity_in_source", "failed", f"{' and '.join(missing)} not found in the document text")
    return Check("identity_in_source", "passed", "holder and account number appear in the document")


def reconcile(data: dict, source_text: Optional[str] = None) -> ReconciliationResult:
    result = ReconciliationResult()
    balance_check, delta = check_balance_arithmetic(data)
    result.checks.append(balance_check)
    result.balance_delta = delta
    result.checks.append(check_period_is_ordered(data))
    result.checks.append(check_dates_in_period(data))
    result.checks.append(check_identity_in_source(data, source_text))
    return result
