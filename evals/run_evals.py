"""Run every fixture through the graph and score the result.

    python -m evals.run_evals                 # live calls
    python -m evals.run_evals --mode record   # live calls, responses saved to evals/cassettes
    python -m evals.run_evals --mode replay   # no network, replay recorded responses (CI)

Scores per fixture: closing balance, opening balance, account number,
currency, account holder (case and whitespace folded), transaction count,
transaction sum, statement date, and the expected status or error code.
Writes evals/results.json and prints a table. Exits non-zero if any
fixture's required checks fail, so CI catches a regression in the prompt,
the schema, or the deterministic code around them.
"""

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent
FIXTURES = EVALS_DIR / "fixtures"
CASSETTES = EVALS_DIR / "cassettes"


def configure(mode: str):
    # The graph only accepts files inside the upload dir, so point it at the fixtures.
    os.environ["UPLOAD_DIR"] = str(FIXTURES)
    if mode in ("record", "replay"):
        os.environ["LLM_CASSETTE_MODE"] = mode
        os.environ["LLM_CASSETTE_DIR"] = str(CASSETTES)
    else:
        os.environ.pop("LLM_CASSETTE_MODE", None)


def close(a, b, tol=0.005):
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol


def fold(s):
    return " ".join((s or "").casefold().split())


def digits(s):
    return "".join(ch for ch in (s or "") if ch.isalnum()).casefold()


def score_case(expected: dict, state: dict) -> dict:
    """Return {check_name: bool} for one fixture. Only checks the fixture defines are scored."""
    checks = {}
    if expected.get("expect_error_code"):
        checks["error_code"] = state.get("error_code") == expected["expect_error_code"]
        checks["no_model_call"] = not state.get("llm_calls")
        return checks

    data = state.get("validated_data") or {}
    checks["completed"] = not state.get("error")
    checks["status"] = state.get("status") == expected["expect_status"]
    checks["closing_balance"] = close(data.get("closing_balance"), expected["closing_balance"])
    if expected.get("opening_balance") is not None:
        checks["opening_balance"] = close(data.get("opening_balance"), expected["opening_balance"])
    checks["account_number"] = digits(data.get("account_number")) == digits(expected["account_number"])
    checks["account_holder"] = fold(data.get("account_holder")) == fold(expected["account_holder"])
    checks["currency"] = (data.get("currency") or "").upper() == expected["currency"]
    checks["statement_date"] = data.get("statement_date") == expected["statement_date"]
    txs = data.get("transactions") or []
    checks["transaction_count"] = len(txs) == expected["transaction_count"]
    checks["transactions_sum"] = close(sum(t.get("amount", 0) for t in txs), expected["transactions_sum"], tol=0.01)
    return checks


def run(mode: str, only=None) -> dict:
    configure(mode)
    from agents.statement_extraction.graph import compiled_graph
    from agents.statement_extraction.job import JobResult
    from core.excel import write_workbook

    cases = sorted(p for p in FIXTURES.iterdir() if (p / "expected.json").is_file())
    if only:
        cases = [c for c in cases if c.name in only]

    results, states = [], []
    for folder in cases:
        expected = json.loads((folder / "expected.json").read_text())
        started = time.perf_counter()
        state = dict(compiled_graph.invoke({"file_path": str(folder / "statement.pdf")}))
        wall_ms = int((time.perf_counter() - started) * 1000)
        # In replay mode wall time is meaningless; use the recorded call latency.
        latency_ms = sum(c.get("latency_ms", 0) for c in state.get("llm_calls") or []) if mode == "replay" else wall_ms
        state["file_path"] = str(folder / "statement.pdf")
        states.append(state)
        job = JobResult.from_state(state, latency_ms)
        checks = score_case(expected, state)
        results.append({
            "case": folder.name,
            "description": expected.get("description", ""),
            "checks": checks,
            "passed": all(checks.values()),
            "status": job.status,
            "error_code": job.error_code,
            "escalated": job.escalated,
            "model_used": job.model_used,
            "llm_calls": job.llm_calls,
            "input_tokens": job.input_tokens,
            "output_tokens": job.output_tokens,
            "est_cost_usd": job.est_cost_usd,
            "latency_ms": job.latency_ms,
            "review_reasons": job.review_reasons,
        })

    # Batch-level check: the duplicate fixture must be deduplicated by the workbook.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        counts = write_workbook(states, os.path.join(tmp, "evals.xlsx"), "default")
    dup_expected = sum(1 for c in cases if json.loads((c / "expected.json").read_text()).get("duplicate_of"))
    batch = {"workbook_counts": counts, "duplicates_expected": dup_expected,
             "duplicates_detected": counts["duplicate"] == dup_expected}

    return {"mode": mode, "cases": results, "batch": batch, "summary": summarise(results, batch)}


def summarise(results, batch) -> dict:
    scored = [r for r in results if not r["error_code"]]
    def rate(name):
        applicable = [r for r in scored if name in r["checks"]]
        return {"passed": sum(1 for r in applicable if r["checks"][name]), "of": len(applicable)}
    costs = [r["est_cost_usd"] for r in scored if r["est_cost_usd"] is not None]
    lat = [r["latency_ms"] for r in scored if r["latency_ms"]]
    return {
        "cases": len(results),
        "cases_passed": sum(1 for r in results if r["passed"]),
        "closing_balance": rate("closing_balance"),
        "opening_balance": rate("opening_balance"),
        "account_number": rate("account_number"),
        "account_holder": rate("account_holder"),
        "currency": rate("currency"),
        "statement_date": rate("statement_date"),
        "transaction_count": rate("transaction_count"),
        "transactions_sum": rate("transactions_sum"),
        "status": rate("status"),
        "reconciled_first_attempt": sum(1 for r in scored if r["status"] == "OK" and not r["escalated"]),
        "escalated": sum(1 for r in scored if r["escalated"]),
        "needs_review": sum(1 for r in scored if r["status"] == "NEEDS_REVIEW"),
        "injection_unaffected": next((r["passed"] for r in results if r["case"] == "prompt_injection"), None),
        "duplicates_detected": batch["duplicates_detected"],
        "median_cost_usd": round(statistics.median(costs), 5) if costs else None,
        "total_cost_usd": round(sum(costs), 4) if costs else None,
        "median_latency_ms": int(statistics.median(lat)) if lat else None,
        "p95_latency_ms": sorted(lat)[max(0, round(0.95 * (len(lat) - 1)))] if lat else None,
        "total_input_tokens": sum(r["input_tokens"] for r in results),
        "total_output_tokens": sum(r["output_tokens"] for r in results),
    }


def print_report(report: dict):
    s = report["summary"]
    print(f"\nEval mode: {report['mode']}\n")
    print(f"{'case':<28} {'result':<7} {'status':<13} {'model':<28} {'tok in/out':<13} {'cost':<9} {'ms':>6}  failed checks")
    for r in report["cases"]:
        failed = ", ".join(k for k, v in r["checks"].items() if not v)
        cost = f"${r['est_cost_usd']:.4f}" if r["est_cost_usd"] is not None else "-"
        print(f"{r['case']:<28} {'PASS' if r['passed'] else 'FAIL':<7} {r['status']:<13} {(r['model_used'] or '-'):<28} "
              f"{r['input_tokens']}/{r['output_tokens']:<7} {cost:<9} {r['latency_ms']:>6}  {failed}")
    print()
    for key in ("closing_balance", "opening_balance", "account_number", "account_holder", "currency",
                "statement_date", "transaction_count", "transactions_sum", "status"):
        print(f"  {key:<24} {s[key]['passed']}/{s[key]['of']}")
    print(f"  {'reconciled first try':<24} {s['reconciled_first_attempt']}   escalated {s['escalated']}   needs review {s['needs_review']}")
    print(f"  {'injection unaffected':<24} {s['injection_unaffected']}")
    print(f"  {'duplicate detected':<24} {s['duplicates_detected']}")
    print(f"  {'median cost / statement':<24} ${s['median_cost_usd']}   total ${s['total_cost_usd']}")
    print(f"  {'median latency':<24} {s['median_latency_ms']} ms   p95 {s['p95_latency_ms']} ms")
    print(f"\n  cases passed: {s['cases_passed']}/{s['cases']}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=["live", "record", "replay"], default="live")
    parser.add_argument("--only", nargs="*", help="Fixture names to run")
    parser.add_argument("--out", default=str(EVALS_DIR / "results.json"))
    args = parser.parse_args(argv)

    report = run(args.mode, args.only)
    Path(args.out).write_text(json.dumps(report, indent=2) + "\n")
    print_report(report)
    print(f"\nWrote {args.out}")
    failed = [r["case"] for r in report["cases"] if not r["passed"]]
    if failed or not report["batch"]["duplicates_detected"]:
        print(f"\nFAILED: {failed or 'duplicate detection'}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
