from openpyxl import load_workbook

from core.excel import write_workbook


def result(holder, number, month="2026-08", balance=10.0, status="OK", reasons=None, delta=None, file="f.pdf"):
    return {
        "format_id": "default",
        "file_path": f"/uploads/{file}",
        "status": status,
        "review_reasons": reasons or [],
        "reconciliation": {"balance_delta": delta},
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

    counts = write_workbook(
        [result("Jane Doe", "111"), result("Jane Doe", "111"), result("Bob", "222", month="2026-07"),
         {"error": "boom"}],
        str(out), "default",
    )
    assert counts == {"ok": 2, "needs_review": 0, "duplicate": 1, "failed": 1}

    # Second run: the same account in the same month is a duplicate of a row
    # that already exists on disk, and a row without a date uses --month.
    counts = write_workbook(
        [result("Jane Doe", "111"), result("Zed", None, month=None)],
        str(out), "default", fallback_month="2026-09",
    )
    assert counts == {"ok": 1, "needs_review": 0, "duplicate": 1, "failed": 0}

    wb = load_workbook(out)
    assert sorted(wb.sheetnames) == ["2026-07", "2026-08", "2026-09"]
    assert wb["2026-08"].max_row == 2  # header + Jane once
    assert wb["2026-08"]["A1"].value == "Account Holder"


def test_unreconciled_rows_go_to_the_review_sheet_with_reasons(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIENT_ID", "default")
    out = tmp_path / "book.xlsx"
    counts = write_workbook(
        [result("Jane Doe", "111"),
         result("Ann Off", "333", status="NEEDS_REVIEW", reasons=["balance_arithmetic: delta +12.00"], delta=12.0, file="ann.pdf")],
        str(out), "default",
    )
    assert counts == {"ok": 1, "needs_review": 1, "duplicate": 0, "failed": 0}
    wb = load_workbook(out)
    assert "Needs review" in wb.sheetnames
    ws = wb["Needs review"]
    header = [c.value for c in ws[1]]
    assert header[-3:] == ["Reasons", "Balance delta", "Source file"]
    row = [c.value for c in ws[2]]
    assert row[0] == "Ann Off"
    assert row[-3:] == ["balance_arithmetic: delta +12.00", 12.0, "ann.pdf"]
    # The reconciled row is not on the review sheet and the review row is not on the month sheet.
    assert wb["2026-08"].max_row == 2
