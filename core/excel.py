"""Excel workbook writer for batch results.

One writer, used by run_batch. Reconciled rows are grouped into one sheet
per statement month and deduplicated on (account_holder, account_number)
within a sheet, including rows already present from an earlier run. Rows
that did not reconcile go to a "Needs review" sheet with the reasons and
the balance delta, so a reviewer sees them instead of losing them.
"""

REVIEW_SHEET = "Needs review"
REVIEW_EXTRA_HEADERS = ["Reasons", "Balance delta", "Source file"]

import logging
import os

from openpyxl import Workbook, load_workbook

from core.client_config import load_format_config

logger = logging.getLogger(__name__)


def _existing_keys(ws, columns):
    ah_idx = columns.index("account_holder") if "account_holder" in columns else None
    an_idx = columns.index("account_number") if "account_number" in columns else None
    keys = set()
    for row in ws.iter_rows(min_row=2, values_only=True):
        holder = row[ah_idx] if ah_idx is not None else None
        number = row[an_idx] if an_idx is not None else None
        if holder:
            keys.add((holder, number))
    return keys


def _autofit(ws, columns, label_by_name):
    for i, col_name in enumerate(columns, start=1):
        values = [label_by_name.get(col_name, col_name)]
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row[i - 1] is not None:
                values.append(str(row[i - 1]))
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = (
            int(max(len(v) for v in values) * 1.2) + 4
        )


def write_workbook(results, output_path, client_id, fallback_month=None):
    """Write every extracted result to the workbook.

    Returns a dict of counts: ok, needs_review, duplicate, failed.
    """
    counts = {"ok": 0, "needs_review": 0, "duplicate": 0, "failed": 0}
    workbook_dirty = False
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    if os.path.exists(output_path):
        wb = load_workbook(output_path)
    else:
        wb = Workbook()
        wb.remove(wb.active)

    keys_by_sheet = {}
    columns_by_sheet = {}

    for result in results:
        if result.get("error"):
            counts["failed"] += 1
            continue

        config = load_format_config(client_id, result.get("format_id") or "default")
        columns = config["excel_output"]["columns"]
        label_by_name = {f["name"]: f.get("label", f["name"]) for f in config["fields"]}
        headers = [label_by_name.get(col, col) for col in columns]

        data = result.get("validated_data", {})
        needs_review = result.get("status") == "NEEDS_REVIEW"
        if needs_review:
            sheet = REVIEW_SHEET
            headers = headers + REVIEW_EXTRA_HEADERS
        else:
            sheet = result.get("statement_month") or fallback_month or "Unsorted"

        if sheet not in wb.sheetnames:
            ws = wb.create_sheet(title=sheet)
            ws.append(headers)
            ws.freeze_panes = "A2"
            keys_by_sheet[sheet] = set()
        else:
            ws = wb[sheet]
            keys_by_sheet.setdefault(sheet, _existing_keys(ws, columns))
        columns_by_sheet[sheet] = (columns, label_by_name)

        # The key must be recoverable from the sheet on the next run, so it
        # only uses account_number when that column is actually written.
        number = data.get("account_number") if "account_number" in columns else None
        key = (data.get("account_holder"), number)
        if key in keys_by_sheet[sheet]:
            counts["duplicate"] += 1
            logger.info("Skipping duplicate row in %s", sheet)
            continue

        row = [data.get(col) for col in columns]
        if needs_review:
            delta = (result.get("reconciliation") or {}).get("balance_delta")
            row += ["; ".join(result.get("review_reasons") or []), delta,
                    os.path.basename(result.get("file_path") or "")]
            counts["needs_review"] += 1
        else:
            counts["ok"] += 1
        ws.append(row)
        keys_by_sheet[sheet].add(key)
        workbook_dirty = True

    for sheet, (columns, label_by_name) in columns_by_sheet.items():
        extra = REVIEW_EXTRA_HEADERS if sheet == REVIEW_SHEET else []
        _autofit(wb[sheet], columns + extra, label_by_name)

    if workbook_dirty or not os.path.exists(output_path):
        wb.save(output_path)
    return counts
