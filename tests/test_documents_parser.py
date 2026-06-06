from pathlib import Path

import pytest

from paper_rag.documents.parser import normalize_page_text, scan_source_directory
from paper_rag.exceptions import DocumentParseError

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "parser_scan"


def test_scan_source_directory_finds_pdfs_and_skips_other_files() -> None:
    pdf_path = FIXTURE_DIR / "paper.PDF"
    txt_path = FIXTURE_DIR / "notes.txt"

    pdfs, skipped = scan_source_directory(FIXTURE_DIR)

    assert pdfs == [pdf_path]
    assert len(skipped) == 1
    assert skipped[0].source_path == txt_path
    assert skipped[0].reason == "not a PDF file"


def test_scan_source_directory_rejects_missing_directory() -> None:
    with pytest.raises(DocumentParseError):
        scan_source_directory(FIXTURE_DIR / "missing")


def test_normalize_page_text() -> None:
    assert normalize_page_text(" line one \r\nline two  \r\n") == "line one\nline two"
