import os
from agents.statement_extraction.nodes import node_validate_file
from agents.statement_extraction.nodes import sanitize_text
from agents.statement_extraction.schema import Transaction
from core.config import ALLOWED_UPLOAD_DIR, PROJECT_ROOT
from core.llm import clean_json_response
import pytest


def upload(name: str) -> str:
    return os.path.join(ALLOWED_UPLOAD_DIR, name)

def test_rejects_non_pdf():
    state = {"file_path": upload("statement.txt")}
    result = node_validate_file(state)
    assert result["error"] == "File must be a PDF"

def test_accepts_uppercase_pdf_extension():
    state = {"file_path": upload("STATEMENT.PDF")}
    result = node_validate_file(state)
    # Extension check passes; the file does not exist, so the error
    # must be about existence, not about the file type.
    assert result["error"] != "File must be a PDF"

def test_rejects_missing_file():
    state = {"file_path": upload("does_not_exist.pdf")}
    result = node_validate_file(state)
    assert "File not found" in result["error"]

def test_rejects_path_outside_allowed_dir():
    state = {"file_path": "../../../etc/passwd.pdf"}
    result = node_validate_file(state)
    assert "Access denied" in result["error"]

def test_outside_paths_are_indistinguishable_whether_they_exist():
    # Containment is checked before existence, so a caller cannot use the
    # error message to probe which files exist on the host.
    real = node_validate_file({"file_path": "/etc/hosts.pdf"})["error"]
    fake = node_validate_file({"file_path": "/etc/nope-does-not-exist.pdf"})["error"]
    assert real == fake == "Access denied: file outside allowed directory"

def test_errors_do_not_echo_the_supplied_path():
    for path in ("../../../etc/passwd.pdf", upload("does_not_exist.pdf")):
        assert path not in node_validate_file({"file_path": path})["error"]

def test_upload_dir_is_anchored_to_project_root_not_cwd(tmp_path, monkeypatch):
    # A relative "uploads/x.pdf" must not become valid just because the
    # process happens to be started from a folder that contains uploads/.
    (tmp_path / "uploads").mkdir()
    (tmp_path / "uploads" / "x.pdf").write_bytes(b"%PDF-1.4")
    monkeypatch.chdir(tmp_path)
    result = node_validate_file({"file_path": "uploads/x.pdf"})
    assert result["error"] == "Access denied: file outside allowed directory"
    assert ALLOWED_UPLOAD_DIR.startswith(str(PROJECT_ROOT))

def test_clean_json_strips_markdown_fences():
    raw = '```json\n{"account_holder": "Jane Doe"}\n```'
    result = clean_json_response(raw)
    assert result == '{"account_holder": "Jane Doe"}'

def test_sanitize_text_removes_invisible_characters():
    dirty = "Account\u200b\u200bHolder"
    result = sanitize_text(dirty)
    assert result == "AccountHolder"

def test_transaction_rejects_bad_date_format():
    with pytest.raises(Exception):
        Transaction(date="31-31-2025", description="ATM withdrawal", amount=-50.0)