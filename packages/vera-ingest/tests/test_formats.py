import pytest

from vera_ingest.formats import (
    pick_parser_for_suffix,
    resolve_ingest_parser,
    source_mime_type,
    source_suffix,
)
from vera_ingest.markdown import ensure_registered as ensure_markdown
from vera_ingest_pymupdf import ensure_registered as ensure_pymupdf


def test_source_mime_type_covers_pdf_markdown_office_html():
    assert source_suffix("Manual.PDF") == "pdf"
    assert source_mime_type("manual.pdf") == "application/pdf"
    assert source_mime_type("notes.md") == "text/markdown"
    assert source_mime_type("notes.markdown") == "text/markdown"
    assert (
        source_mime_type("memo.docx")
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert (
        source_mime_type("slides.pptx")
        == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
    assert (
        source_mime_type("budget.xlsx")
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert source_mime_type("page.html") == "text/html"
    assert source_mime_type("page.htm") == "text/html"
    assert source_mime_type("README") == "application/octet-stream"
    assert source_mime_type("notes.unknownext") == "application/octet-stream"


def test_resolve_ingest_parser_suffix_and_mismatch_edges():
    ensure_pymupdf()
    ensure_markdown()
    assert resolve_ingest_parser("manual.pdf") == "pymupdf"
    assert resolve_ingest_parser("notes.md") == "markdown"
    assert resolve_ingest_parser("notes.md", parser="   ") == "markdown"
    assert pick_parser_for_suffix("pdf") == "pymupdf"
    with pytest.raises(ValueError, match="Cannot infer"):
        resolve_ingest_parser("README")
    with pytest.raises(ValueError, match="No installed ingest pipeline supports"):
        resolve_ingest_parser("notes.txt")
    with pytest.raises(ValueError, match="does not support .html"):
        resolve_ingest_parser("notes.html", parser="markdown")
    with pytest.raises(ValueError, match="does not support .pdf"):
        resolve_ingest_parser("manual.pdf", parser="markdown")
