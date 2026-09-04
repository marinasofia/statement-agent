"""One record per processed file: what happened, what it cost, how long it took.

The batch writes these to outputs/run_<timestamp>.jsonl. It is the answer
to "what did last night's run cost and which files need a human", and it
contains no statement content: file basename, ids, status, counts.
"""

import os
from typing import Optional

from pydantic import BaseModel

from core.pricing import estimate_cost_usd


class JobResult(BaseModel):
    file: str                      # basename only, never the full path
    job_id: Optional[str] = None
    status: str                    # OK, NEEDS_REVIEW, DUPLICATE, FAILED
    error_code: Optional[str] = None
    error: Optional[str] = None
    format_id: Optional[str] = None
    statement_month: Optional[str] = None
    review_reasons: list[str] = []
    balance_delta: Optional[float] = None
    escalated: bool = False
    model_used: Optional[str] = None   # model whose output was accepted
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    est_cost_usd: Optional[float] = None
    latency_ms: int = 0

    @classmethod
    def from_state(cls, state: dict, latency_ms: int) -> "JobResult":
        calls = state.get("llm_calls") or []
        input_tokens = sum(c.get("input_tokens", 0) for c in calls)
        output_tokens = sum(c.get("output_tokens", 0) for c in calls)
        cost = None
        if calls:
            per_call = [estimate_cost_usd(c.get("model", ""), c.get("input_tokens", 0), c.get("output_tokens", 0)) for c in calls]
            cost = round(sum(per_call), 6) if all(p is not None for p in per_call) else None

        if state.get("error"):
            status = "FAILED"
        elif state.get("duplicate"):
            status = "DUPLICATE"
        else:
            status = state.get("status") or "OK"

        return cls(
            file=os.path.basename(state.get("file_path") or ""),
            job_id=state.get("job_id"),
            status=status,
            error_code=state.get("error_code"),
            error=state.get("error"),
            format_id=state.get("format_id"),
            statement_month=state.get("statement_month"),
            review_reasons=list(state.get("review_reasons") or []),
            balance_delta=(state.get("reconciliation") or {}).get("balance_delta"),
            escalated=bool(state.get("escalated")),
            model_used=calls[-1].get("model") if calls and not state.get("error") else None,
            llm_calls=len(calls),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            est_cost_usd=cost,
            latency_ms=latency_ms,
        )


def percentile(values: list[int], pct: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(pct / 100 * (len(ordered) - 1))))
    return ordered[index]


def summarise(jobs: list[JobResult]) -> dict:
    by_status = {}
    for job in jobs:
        by_status[job.status] = by_status.get(job.status, 0) + 1
    costs = [j.est_cost_usd for j in jobs if j.est_cost_usd is not None]
    latencies = [j.latency_ms for j in jobs]
    return {
        "files": len(jobs),
        "by_status": by_status,
        "escalated": sum(1 for j in jobs if j.escalated),
        "llm_calls": sum(j.llm_calls for j in jobs),
        "input_tokens": sum(j.input_tokens for j in jobs),
        "output_tokens": sum(j.output_tokens for j in jobs),
        "est_cost_usd": round(sum(costs), 4) if costs else None,
        "latency_ms_p50": percentile(latencies, 50),
        "latency_ms_p95": percentile(latencies, 95),
    }
