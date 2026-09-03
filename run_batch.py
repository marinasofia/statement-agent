import argparse
import os
import glob
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.config import EXCEL_OUTPUT_PATH, ALLOWED_UPLOAD_DIR
from core.client_config import get_client_id
from core.excel import write_workbook
from agents.statement_extraction.graph import compiled_graph

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
    args = parser.parse_args(argv)
    if args.month and not MONTH_PATTERN.match(args.month):
        parser.error("--month must look like YYYY-MM")
    if args.workers < 1:
        parser.error("--workers must be at least 1")
    return args

def process_pdf(pdf_path: str) -> dict:
    try:
        result = compiled_graph.invoke({'file_path': pdf_path})
        return result
    except Exception as e:
        logger.error(f"Unhandled error on {pdf_path}: {e}")
        return {'file_path': pdf_path, 'error': str(e)}

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
            if result.get("error"):
                print(f"[{completed}/{len(pdf_files)}] FAILED  {pdf_name}: {result.get('error')}")
            else:
                data = result.get("validated_data", {})
                print(f"[{completed}/{len(pdf_files)}] OK      {pdf_name}: {data.get('account_holder')} | {data.get('closing_balance')}")

    # No interactive prompt: an unattended run must never block on stdin.
    # Rows without a parseable date go to --month if given, else "Unsorted".
    success, skipped, failed = write_workbook(results, args.output, get_client_id(), args.month)

    print(f"\nDone. Output: {args.output}")
    print(f"  Written:   {success}")
    print(f"  Skipped:   {skipped} (duplicates)")
    print(f"  Failed:    {failed}")

if __name__ == "__main__":
    main()