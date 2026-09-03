"""Excel workbook writer for batch results.

One writer, used by run_batch. Rows are grouped into one sheet per
statement month and deduplicated on (account_holder, account_number)
within a sheet, including rows already present from an earlier run.
"""

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
    """Write every successful result to the workbook. Returns (written, skipped, failed)."""
    written = skipped = failed = 0
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
            failed += 1
            continue

        config = load_format_config(client_id, result.get("format_id") or "default")
        columns = config["excel_output"]["columns"]
        label_by_name = {f["name"]: f.get("label", f["name"]) for f in config["fields"]}
        headers = [label_by_name.get(col, col) for col in columns]

        data = result.get("validated_data", {})
        month = result.get("statement_month") or fallback_month or "Unsorted"

        if month not in wb.sheetnames:
            ws = wb.create_sheet(title=month)
            ws.append(headers)
            ws.freeze_panes = "A2"
            keys_by_sheet[month] = set()
        else:
            ws = wb[month]
            keys_by_sheet.setdefault(month, _existing_keys(ws, columns))
        columns_by_sheet[month] = (columns, label_by_name)

        # The key must be recoverable from the sheet on the next run, so it
        # only uses account_number when that column is actually written.
        number = data.get("account_number") if "account_number" in columns else None
        key = (data.get("account_holder"), number)
        if key in keys_by_sheet[month]:
            skipped += 1
            logger.info("Skipping duplicate row in %s", month)
            continue

        ws.append([data.get(col) for col in columns])
        keys_by_sheet[month].add(key)
        written += 1
        workbook_dirty = True

    for month, (columns, label_by_name) in columns_by_sheet.items():
        _autofit(wb[month], columns, label_by_name)

    if workbook_dirty or not os.path.exists(output_path):
        wb.save(output_path)
    return written, skipped, failed
