import os
import shutil

import pytest
from reportlab.pdfgen import canvas

from agents.statement_extraction.nodes import (
    detect_format_id,
    node_detect_format,
    node_extract_text,
    node_validate_file,
)
from core.config import ALLOWED_UPLOAD_DIR


def make_pdf(path, lines=(), draw_only=False):
    c = canvas.Canvas(str(path))
    if draw_only:
        c.rect(50, 50, 200, 200, fill=1)
    else:
        y = 800
        for line in lines:
            c.drawString(50, y, line)
            y -= 16
    c.save()


@pytest.fixture
def upload_dir():
    os.makedirs(ALLOWED_UPLOAD_DIR, exist_ok=True)
    created = []
    yield lambda name: created.append(os.path.join(ALLOWED_UPLOAD_DIR, name)) or created[-1]
    for path in created:
        if os.path.exists(path):
            os.remove(path)


def test_extract_text_reads_text_layer(upload_dir):
    path = upload_dir("t_text.pdf")
    make_pdf(path, ["ACME BANK", "Closing balance 12.34"])
    state = node_extract_text(node_validate_file({"file_path": path}))
    assert not state.get("error")
    assert "ACME BANK" in state["raw_text"]
    assert "12.34" in state["raw_text"]


def test_extract_text_rejects_image_only_pdf(upload_dir):
    path = upload_dir("t_scan.pdf")
    make_pdf(path, draw_only=True)
    state = node_extract_text(node_validate_file({"file_path": path}))
    assert state["error"] == "Scanned PDFs not supported yet"


def test_extract_text_does_not_run_after_an_error():
    state = {"error": "File must be a PDF", "file_path": "x"}
    assert node_extract_text(state) == state


FORMATS = [
    {"format_id": "default", "signatures": [], "min_matches": 1},
    {"format_id": "acme", "signatures": ["ACME Bank", "Member FDIC"], "min_matches": 2},
    {"format_id": "globex", "signatures": ["Globex Credit Union"], "min_matches": 1},
]


def test_detect_format_picks_the_best_signature_match():
    assert detect_format_id("Statement from ACME BANK, member fdic", FORMATS) == "acme"
    assert detect_format_id("Globex Credit Union monthly statement", FORMATS) == "globex"


def test_detect_format_requires_min_matches():
    # Only one of ACME's two signatures is present, so it does not qualify.
    assert detect_format_id("ACME Bank statement", FORMATS) == "default"


def test_detect_format_falls_back_to_default_when_nothing_matches():
    assert detect_format_id("Some other bank entirely", FORMATS) == "default"
    assert detect_format_id("", FORMATS) == "default"


def test_detect_format_node_sets_client_and_format(monkeypatch):
    monkeypatch.setenv("CLIENT_ID", "default")
    state = node_detect_format({"raw_text": "anything", "job_id": "j"})
    assert state["client_id"] == "default"
    assert state["format_id"] == "default"
