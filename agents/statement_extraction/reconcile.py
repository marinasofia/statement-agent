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
from typing import Optional

BALANCE_TOLERANCE = 0.01  # one cent: rounding, never a missing row


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

    total = sum(t.get("amount", 0.0) or 0.0 for t in transactions)
    delta = round(opening + total - closing, 2)
    if abs(delta) <= BALANCE_TOLERANCE:
        return Check("balance_arithmetic", "passed", f"opening {opening:.2f} + transactions {total:.2f} = closing {closing:.2f}"), delta
    return Check(
        "balance_arithmetic", "failed",
        f"opening {opening:.2f} + transactions {total:.2f} = {opening + total:.2f}, closing is {closing:.2f} (delta {delta:+.2f})",
    ), delta


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


def reconcile(data: dict) -> ReconciliationResult:
    result = ReconciliationResult()
    balance_check, delta = check_balance_arithmetic(data)
    result.checks.append(balance_check)
    result.balance_delta = delta
    result.checks.append(check_period_is_ordered(data))
    result.checks.append(check_dates_in_period(data))
    return result
