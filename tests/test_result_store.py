"""A crash or a rerun must not pay for the same statement twice."""

import stat

import pytest

import run_batch
from core.result_store import ResultStore
from tests.test_excel import result


def make_pdfs(folder, count):
    for i in range(count):
        (folder / f"s{i}.pdf").write_bytes(f"%PDF synthetic {i}".encode())


class CountingExtractor:
    def __init__(self, crash_on=None, fail_on=()):
        self.calls, self.crash_on, self.fail_on = [], crash_on, set(fail_on)

    def __call__(self, path):
        name = path.rsplit("/", 1)[-1]
        self.calls.append(name)
        if name == self.crash_on:
            raise RuntimeError("synthetic crash")
        if name in self.fail_on:
            return {"file_path": path, "error": "synthetic API outage", "error_code": "API_ERROR"}
        return {**result(name, name), "file_path": path, "raw_text": "SECRET statement text"}


def run(folder, out, extractor, monkeypatch, *extra):
    monkeypatch.setattr(run_batch, "process_pdf", extractor)
    return run_batch.main(["--input", str(folder), "--output", str(out), "--workers", "1", *extra])


def test_rerun_after_a_crash_pays_only_for_unfinished_files(tmp_path, monkeypatch):
    inputs = tmp_path / "in"; inputs.mkdir(); make_pdfs(inputs, 5)
    out = tmp_path / "out" / "book.xlsx"
    with pytest.raises(RuntimeError):
        run(inputs, out, CountingExtractor(crash_on="s3.pdf"), monkeypatch)
    second = CountingExtractor()
    assert run(inputs, out, second, monkeypatch) == 0
    assert sorted(second.calls) == ["s3.pdf", "s4.pdf"]       # s0 to s2 were saved before the crash


def test_unchanged_folder_costs_nothing_the_second_time(tmp_path, monkeypatch):
    inputs = tmp_path / "in"; inputs.mkdir(); make_pdfs(inputs, 3)
    out = tmp_path / "out" / "book.xlsx"
    run(inputs, out, CountingExtractor(), monkeypatch)
    again = CountingExtractor()
    assert run(inputs, out, again, monkeypatch) == 0
    assert again.calls == []
    fresh = CountingExtractor()
    run(inputs, out, fresh, monkeypatch, "--fresh")
    assert len(fresh.calls) == 3


def test_failures_are_retried_and_text_is_never_stored(tmp_path, monkeypatch):
    inputs = tmp_path / "in"; inputs.mkdir(); make_pdfs(inputs, 2)
    out = tmp_path / "out" / "book.xlsx"
    run(inputs, out, CountingExtractor(fail_on={"s1.pdf"}), monkeypatch)
    retry = CountingExtractor()
    run(inputs, out, retry, monkeypatch)
    assert retry.calls == ["s1.pdf"]
    db = out.parent / ".statement-agent-results.sqlite"
    assert b"SECRET statement text" not in db.read_bytes()
    assert stat.S_IMODE(db.stat().st_mode) == 0o600


def test_store_skips_failed_states(tmp_path):
    store = ResultStore(tmp_path / "r.sqlite")
    assert store.save("abc", {"error": "boom"}) is False
    assert store.get("abc") is None
