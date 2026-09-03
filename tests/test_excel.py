from openpyxl import load_workbook

from core.excel import write_workbook


def result(holder, number, month="2026-08", balance=10.0):
    return {
        "format_id": "default",
        "statement_month": month,
        "validated_data": {
            "account_holder": holder,
            "account_number": number,
            "closing_balance": balance,
            "currency": "USD",
            "bank_name": "ACME",
            "statement_date": f"{month}-31",
        },
    }


def test_rows_group_by_month_and_dedup_across_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIENT_ID", "default")
    out = tmp_path / "book.xlsx"

    written, skipped, failed = write_workbook(
        [result("Jane Doe", "111"), result("Jane Doe", "111"), result("Bob", "222", month="2026-07"),
         {"error": "boom"}],
        str(out), "default",
    )
    assert (written, skipped, failed) == (2, 1, 1)

    # Second run: the same account in the same month is a duplicate of a row
    # that already exists on disk, and a row without a date uses --month.
    written, skipped, failed = write_workbook(
        [result("Jane Doe", "111"), result("Zed", None, month=None)],
        str(out), "default", fallback_month="2026-09",
    )
    assert (written, skipped, failed) == (1, 1, 0)

    wb = load_workbook(out)
    assert sorted(wb.sheetnames) == ["2026-07", "2026-08", "2026-09"]
    assert wb["2026-08"].max_row == 2  # header + Jane once
    assert wb["2026-08"]["A1"].value == "Account Holder"
