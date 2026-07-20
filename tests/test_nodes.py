from agents.statement_extraction.nodes import node_validate_file
from agents.statement_extraction.nodes import sanitize_text
from agents.statement_extraction.schema import Transaction
from core.llm import clean_json_response
import pytest

def test_rejects_non_pdf():
    state = {"file_path": "uploads/statement.txt"}
    result = node_validate_file(state)
    assert result["error"] == "File must be a PDF"

def test_accepts_uppercase_pdf_extension():
    state = {"file_path": "uploads/STATEMENT.PDF"}
    result = node_validate_file(state)
    # Extension check passes; the file does not exist, so the error
    # must be about existence, not about the file type.
    assert result["error"] != "File must be a PDF"

def test_rejects_missing_file():
    state = {"file_path": "uploads/does_not_exist.pdf"}
    result = node_validate_file(state)
    assert "File not found" in result["error"]

def test_rejects_path_outside_allowed_dir():
    state = {"file_path": "../../../etc/passwd.pdf"}
    result = node_validate_file(state)
    assert result["error"] is not None

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