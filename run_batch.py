import argparse
import json
import os
import glob
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from core.config import EXCEL_OUTPUT_PATH, ALLOWED_UPLOAD_DIR
from core.client_config import get_client_id
from core.excel import write_workbook
from agents.statement_extraction.graph import compiled_graph
from agents.statement_extraction.job import JobResult, summarise

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

DEFAULT_WORKERS = 5
MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Extract every PDF in a folder into one Excel workbook."
    )
    parser.add_argument("--input", default=ALLOWED_UPLOAD_DIR,
                        help="Folder of PDF statements (default: the allowed upload dir)")
    parser.add_argument("--output", default=EXCEL_OUTPUT_PATH,
                        help="Workbook to create or append to")
    parser.add_argument("--month", default=None,
                        help="Sheet to use for statements that carry no parseable date, as YYYY-MM. "
                             "Without it those rows land on an 'Unsorted' sheet.")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help=f"Concurrent extractions (default {DEFAULT_WORKERS})")
    parser.add_argument("--verbose", action="store_true",
                        help="Print account holder and balance per file. Off by default so "
                             "statement content stays out of terminal logs.")
    args = parser.parse_args(argv)
    if args.month and not MONTH_PATTERN.match(args.month):
        parser.error("--month must look like YYYY-MM")
    if args.workers < 1:
        parser.error("--workers must be at least 1")
    return args

def process_pdf(pdf_path: str) -> dict:
    started = time.perf_counter()
    try:
        result = dict(compiled_graph.invoke({'file_path': pdf_path}))
    except Exception as e:
        logger.error(f"Unhandled error on {os.path.basename(pdf_path)}: {e}")
        result = {'file_path': pdf_path, 'error': str(e), 'error_code': 'UNHANDLED'}
    result['latency_ms'] = int((time.perf_counter() - started) * 1000)
    return result


def write_run_log(jobs, summary, output_path):
    """One JSON line per file plus a final summary line, next to the workbook."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = os.path.join(os.path.dirname(output_path) or ".", f"run_{stamp}.jsonl")
    with open(log_path, "w", encoding="utf-8") as f:
        for job in jobs:
            f.write(job.model_dump_json() + "\n")
        f.write(json.dumps({"summary": summary}) + "\n")
    return log_path

def main(argv=None):
    args = parse_args(argv)
    pdf_files = sorted(
        glob.glob(os.path.join(args.input, "*.pdf")) + glob.glob(os.path.join(args.input, "*.PDF"))
    )

    if not pdf_files:
        print(f"No PDFs found in {args.input}")
        return

    print(f"Found {len(pdf_files)} PDFs. Processing with {args.workers} workers...")

    results = []
    completed = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_pdf, pdf): pdf for pdf in pdf_files}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            completed += 1
            pdf_name = os.path.basename(futures[future])
            prefix = f"[{completed}/{len(pdf_files)}]"
            if result.get("error"):
                print(f"{prefix} FAILED        {pdf_name}: {result.get('error_code')}: {result.get('error')}")
            elif result.get("status") == "NEEDS_REVIEW":
                print(f"{prefix} NEEDS REVIEW  {pdf_name}: {'; '.join(result.get('review_reasons') or [])}")
            else:
                tag = "OK (escalated)" if result.get("escalated") else "OK"
                detail = ""
                if args.verbose:
                    data = result.get("validated_data", {})
                    detail = f": {data.get('account_holder')} | {data.get('closing_balance')} {data.get('currency') or ''}"
                print(f"{prefix} {tag:<13} {pdf_name}{detail}")

    # No interactive prompt: an unattended run must never block on stdin.
    # Rows without a parseable date go to --month if given, else "Unsorted".
    counts = write_workbook(results, args.output, get_client_id(), args.month)
    jobs = [JobResult.from_state(r, r.get("latency_ms", 0)) for r in results]
    summary = summarise(jobs)
    log_path = write_run_log(jobs, summary, args.output)

    cost = f"${summary['est_cost_usd']:.4f}" if summary["est_cost_usd"] is not None else "n/a"
    print(f"\nDone. Workbook: {args.output}")
    print(f"      Run log:  {log_path}")
    print(f"  Reconciled:    {counts['ok']}  ({summary['escalated']} after escalation)")
    print(f"  Needs review:  {counts['needs_review']} (on the 'Needs review' sheet)")
    print(f"  Duplicates:    {counts['duplicate']}")
    print(f"  Failed:        {counts['failed']}")
    print(f"  Model calls:   {summary['llm_calls']}  tokens in {summary['input_tokens']:,} / out {summary['output_tokens']:,}  est. cost {cost}")
    print(f"  Latency:       p50 {summary['latency_ms_p50']} ms, p95 {summary['latency_ms_p95']} ms")

if __name__ == "__main__":
    main()