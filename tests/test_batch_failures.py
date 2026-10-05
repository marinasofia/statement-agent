"""Batch outcome logs must survive workbook failures without model calls."""

import json
from unittest.mock import Mock

import run_batch
from tests.test_excel import result


def test_output_failure_keeps_extraction_evidence(tmp_path, monkeypatch):
    (tmp_path / "synthetic.pdf").touch()
    monkeypatch.setattr(run_batch, "process_pdf", lambda _: result("Example", "111"))
    monkeypatch.setattr(
        run_batch, "write_workbook", Mock(side_effect=OSError("Synthetic disk error"))
    )
    target = tmp_path / "output" / "book.xlsx"
    assert run_batch.main(["--input", str(tmp_path), "--output", str(target)]) == 1
    logs = list(target.parent.glob("run_*.jsonl"))
    assert len(logs) == 1
    lines = [json.loads(line) for line in logs[0].read_text().splitlines()]
    assert len(lines) == 2
    assert lines[-1]["summary"]["output_status"] == "FAILED"
    assert lines[-1]["summary"]["output_error_code"] == "OSError"
    assert not target.exists()


def test_all_failed_batch_has_log_workbook_and_nonzero_status(tmp_path, monkeypatch):
    (tmp_path / "synthetic.pdf").touch()
    monkeypatch.setattr(
        run_batch,
        "process_pdf",
        lambda path: {"file_path": path, "error": "Failed", "error_code": "SYNTHETIC"},
    )
    target = tmp_path / "book.xlsx"
    assert run_batch.main(["--input", str(tmp_path), "--output", str(target)]) == 1
    assert target.is_file() and len(list(tmp_path.glob("run_*.jsonl"))) == 1


def test_run_logs_are_unique_and_temporary_files_are_removed(tmp_path):
    first = run_batch.write_run_log([], {}, tmp_path / "book.xlsx")
    second = run_batch.write_run_log([], {}, tmp_path / "book.xlsx")
    assert first != second
    assert len(list(tmp_path.iterdir())) == 2


def test_log_failure_returns_nonzero(tmp_path, monkeypatch):
    (tmp_path / "synthetic.pdf").touch()
    monkeypatch.setattr(run_batch, "process_pdf", lambda _: result("Example", "111"))
    monkeypatch.setattr(
        run_batch, "write_run_log", Mock(side_effect=PermissionError("Denied"))
    )
    assert (
        run_batch.main(
            ["--input", str(tmp_path), "--output", str(tmp_path / "book.xlsx")]
        )
        == 1
    )


def test_review_abort_cancels_queued_extractions(tmp_path, monkeypatch):
    """A failed review save stops the batch without paying for the files still queued."""
    import threading, time
    for i in range(10):
        (tmp_path / f"s{i}.pdf").write_bytes(f"%PDF synthetic {i}".encode())
    calls, lock = [], threading.Lock()

    def fake_process(path):
        time.sleep(0.05)
        with lock:
            calls.append(path)
        return {"file_path": path, "error": None, "validated_data": None}

    class BrokenQueue:
        def __init__(self, *_): pass
        def list(self): return []
        def add(self, *_): raise ValueError("synthetic write failure")

    monkeypatch.setattr(run_batch, "process_pdf", fake_process)
    monkeypatch.setattr(run_batch, "ReviewQueue", BrokenQueue)
    monkeypatch.setattr(run_batch, "ALLOWED_UPLOAD_DIR", str(tmp_path))
    rc = run_batch.main(["--input", str(tmp_path), "--review-db", str(tmp_path / "q.sqlite"), "--workers", "2"])
    assert rc == 1
    assert len(calls) <= 4      # at most the jobs already running when the failure arrived
