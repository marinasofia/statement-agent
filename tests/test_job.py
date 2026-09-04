import json

from agents.statement_extraction.job import JobResult, summarise, percentile
from core.pricing import estimate_cost_usd


def test_pricing_known_and_unknown_models():
    assert estimate_cost_usd("claude-haiku-4-5-20251001", 1_000_000, 0) == 1.0
    assert estimate_cost_usd("claude-sonnet-5", 0, 1_000_000) == 10.0
    assert estimate_cost_usd("some-future-model", 10, 10) is None


def base_state(**over):
    state = {
        "file_path": "/srv/uploads/private name.pdf", "job_id": "j1", "status": "OK", "format_id": "default",
        "statement_month": "2026-08", "escalated": False, "reconciliation": {"balance_delta": 0.0},
        "llm_calls": [{"attempt": 1, "model": "claude-haiku-4-5-20251001", "input_tokens": 1000, "output_tokens": 200, "stop_reason": "end_turn"}],
        "validated_data": {"account_holder": "Jane Doe", "account_number": "111"},
    }
    state.update(over)
    return state


def test_ok_job_record_has_cost_and_no_statement_content():
    job = JobResult.from_state(base_state(), latency_ms=1234)
    assert job.status == "OK"
    assert job.file == "private name.pdf"
    assert job.model_used == "claude-haiku-4-5-20251001"
    assert job.est_cost_usd == 0.002          # 1000 in at $1/M + 200 out at $5/M
    assert job.latency_ms == 1234
    dumped = job.model_dump_json()
    assert "Jane Doe" not in dumped and "111" not in dumped and "/srv" not in dumped


def test_escalated_job_sums_both_calls_and_names_the_accepted_model():
    calls = [
        {"attempt": 1, "model": "claude-haiku-4-5-20251001", "input_tokens": 1000, "output_tokens": 200},
        {"attempt": 1, "model": "claude-sonnet-5", "input_tokens": 1000, "output_tokens": 300},
    ]
    job = JobResult.from_state(base_state(llm_calls=calls, escalated=True), 5000)
    assert job.llm_calls == 2 and job.input_tokens == 2000 and job.output_tokens == 500
    assert job.model_used == "claude-sonnet-5"
    assert job.est_cost_usd == round(0.002 + 0.002 + 0.003, 6)


def test_failed_needs_review_and_duplicate_statuses():
    failed = JobResult.from_state(base_state(error="boom", error_code="TRUNCATED_OUTPUT", status=None), 10)
    assert failed.status == "FAILED" and failed.error_code == "TRUNCATED_OUTPUT" and failed.model_used is None
    review = JobResult.from_state(base_state(status="NEEDS_REVIEW", review_reasons=["balance_arithmetic: off"], reconciliation={"balance_delta": -12.0}), 10)
    assert review.status == "NEEDS_REVIEW" and review.balance_delta == -12.0
    dup = JobResult.from_state(base_state(duplicate=True), 10)
    assert dup.status == "DUPLICATE"


def test_unknown_model_makes_cost_none_rather_than_wrong():
    job = JobResult.from_state(base_state(llm_calls=[{"model": "mystery", "input_tokens": 5, "output_tokens": 5}]), 1)
    assert job.est_cost_usd is None


def test_summary_counts_tokens_cost_and_percentiles():
    jobs = [
        JobResult.from_state(base_state(), 100),
        JobResult.from_state(base_state(status="NEEDS_REVIEW"), 300),
        JobResult.from_state(base_state(error="x", error_code="SCANNED", llm_calls=[]), 20),
    ]
    s = summarise(jobs)
    assert s["files"] == 3
    assert s["by_status"] == {"OK": 1, "NEEDS_REVIEW": 1, "FAILED": 1}
    assert s["llm_calls"] == 2 and s["input_tokens"] == 2000
    assert s["est_cost_usd"] == 0.004
    assert s["latency_ms_p50"] == 100 and s["latency_ms_p95"] == 300


def test_percentile_edges():
    assert percentile([], 50) == 0
    assert percentile([7], 95) == 7


def test_run_log_is_jsonl_with_a_summary_line(tmp_path):
    from run_batch import write_run_log
    jobs = [JobResult.from_state(base_state(), 100)]
    path = write_run_log(jobs, summarise(jobs), str(tmp_path / "book.xlsx"))
    lines = open(path).read().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["status"] == "OK"
    assert "summary" in json.loads(lines[1])
