from pathlib import Path

import pytest

from vera_doc import VeraDocument
from vera_ingest import (
    batch_convert,
    convert,
    describe_ingest_pipeline,
    get_ingest_pipeline,
    list_ingest_pipelines,
    reset_ingest_pipeline_registry,
    resolve_ingest_parser,
)
from vera_ingest.markdown import ensure_registered, parse_markdown
from vera_ingest.viewer import export_source_document, get_chunk_regions, get_source_document
from vera_ingest_pymupdf import ensure_registered as ensure_pymupdf_registered

SAMPLE = """\
# Stormwater Manual

## 4.2 Detention Design

Ponds must detain the 25-year storm on site.

- First list item
- Second list item

```python
print("hello")
```

| Size | Volume |
| --- | --- |
| Small | 1 ac-ft |
| Large | 10 ac-ft |
"""


@pytest.fixture
def markdown_ready():
    reset_ingest_pipeline_registry()
    ensure_pymupdf_registered()
    ensure_registered()
    yield
    reset_ingest_pipeline_registry()


def _write_manual(path: Path, body: str = SAMPLE) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def test_markdown_parser_strips_bom_and_keeps_frontmatter():
    text = "\ufeff---\ntitle: Manual\n---\n\n# Heading\n\nBody text.\n"
    pages, blocks = parse_markdown(text)
    assert not pages[0].text.startswith("\ufeff")
    assert pages[0].text.startswith("---")
    assert blocks[0].parsed.block_type == "paragraph"
    assert "title: Manual" in blocks[0].parsed.text
    heading = next(item for item in blocks if item.parsed.block_type == "heading")
    assert heading.parsed.text == "Heading"


def test_markdown_parser_unclosed_fence_emits_code():
    _, blocks = parse_markdown("```python\nprint(1)\n")
    code = next(item for item in blocks if item.parsed.block_type == "code")
    assert "print(1)" in code.parsed.text


def test_markdown_parser_empty_atx_heading_skips_paragraph():
    _, blocks = parse_markdown("#\n\nBody paragraph.\n")
    heading = next(item for item in blocks if item.parsed.block_type == "heading")
    assert heading.parsed.text == ""
    assert heading.parsed.heading_level == 1
    paragraphs = [item for item in blocks if item.parsed.block_type == "paragraph"]
    assert [item.parsed.text for item in paragraphs] == ["Body paragraph."]


def test_markdown_parser_setext_heading():
    _, blocks = parse_markdown("Detention\n=========\n\nPonds detain.\n")
    heading = next(item for item in blocks if item.parsed.block_type == "heading")
    assert heading.parsed.text == "Detention"
    assert heading.parsed.heading_level == 1


def test_markdown_parser_splits_headings_tables_and_code():
    pages, blocks = parse_markdown(SAMPLE)
    assert len(pages) == 1
    types = [item.parsed.block_type for item in blocks]
    assert types.count("heading") >= 2
    assert "table" in types
    assert "code" in types
    heading = next(item for item in blocks if item.parsed.heading_level == 2)
    assert heading.parsed.text == "4.2 Detention Design"
    assert heading.region()["kind"] == "text_span"
    assert heading.region()["start"]["line"] == 3


def test_markdown_pipeline_is_registered(markdown_ready):
    assert "markdown" in list_ingest_pipelines()
    assert get_ingest_pipeline("markdown") is get_ingest_pipeline("markdown:default")
    descriptor = describe_ingest_pipeline("markdown")
    assert descriptor.capabilities.source_formats == ("md", "markdown")
    assert descriptor.capabilities.ocr_supported is False


def test_resolve_parser_picks_markdown_for_md_and_rejects_pymupdf(markdown_ready, tmp_path):
    notes = _write_manual(tmp_path / "notes.md")
    assert resolve_ingest_parser(notes) == "markdown"
    with pytest.raises(ValueError, match="does not support .md"):
        resolve_ingest_parser(notes, parser="pymupdf")


def test_convert_markdown_and_search(markdown_ready, tmp_path):
    source = _write_manual(tmp_path / "manual.md")
    out = tmp_path / "manual.vera"
    convert(str(source), str(out), model="hashing")

    with VeraDocument.open(str(out)) as document:
        info = document.inspect()
        assert info["parser_name"] == "markdown"
        assert info["source_file_name"] == "manual.md"
        assert info["source_mime_type"] == "text/markdown"
        hits = document.search("Ponds must detain", mode="keyword", top_k=5)
        matching = [hit for hit in hits if "25-year" in hit.text]
        assert matching
        assert "Detention Design" in (matching[0].heading_path or "")
        regions = get_chunk_regions(document, matching[0].record.id)
        assert regions
        assert regions[0]["kind"] == "text_span"
        assert "bbox" not in regions[0]
        exported = Path(export_source_document(document, str(tmp_path / "exported.md")))
        assert exported.read_text(encoding="utf-8") == SAMPLE
        stored = get_source_document(document)
        assert stored.media_type == "text/markdown"


def test_convert_markdown_without_explicit_parser(markdown_ready, tmp_path):
    source = _write_manual(tmp_path / "notes.md")
    out = tmp_path / "notes.vera"
    convert(str(source), str(out), model="hashing")
    with VeraDocument.open(str(out)) as document:
        assert document.inspect()["parser_name"] == "markdown"


def test_empty_markdown_fails_with_generic_message(markdown_ready, tmp_path):
    source = tmp_path / "empty.md"
    source.write_text("\n\n", encoding="utf-8")
    with pytest.raises(ValueError, match="No searchable text"):
        convert(str(source), str(tmp_path / "empty.vera"), model="hashing")
    assert not (tmp_path / "empty.vera").exists()


def test_batch_convert_mixed_pdf_and_markdown(markdown_ready, tmp_path):
    from helpers.pdfs import make_pdf

    make_pdf(tmp_path / "manual.pdf")
    _write_manual(tmp_path / "notes.md")
    (tmp_path / "ignored.txt").write_text("not converted", encoding="utf-8")

    report = batch_convert(str(tmp_path), model="hashing")
    assert report["discovered"] == 2
    assert report["converted"] == 2
    assert report["failed"] == 0
    assert (tmp_path / "manual.vera").is_file()
    assert (tmp_path / "notes.vera").is_file()

    with VeraDocument.open(str(tmp_path / "notes.vera")) as document:
        assert document.inspect()["parser_name"] == "markdown"
    with VeraDocument.open(str(tmp_path / "manual.vera")) as document:
        assert document.inspect()["parser_name"] == "pymupdf"


def test_batch_convert_parser_markdown_skips_pdfs(markdown_ready, tmp_path):
    from helpers.pdfs import make_pdf

    make_pdf(tmp_path / "manual.pdf")
    _write_manual(tmp_path / "notes.md")
    report = batch_convert(str(tmp_path), model="hashing", parser="markdown")
    assert report["discovered"] == 1
    assert report["converted"] == 1
    assert (tmp_path / "notes.vera").is_file()
    assert not (tmp_path / "manual.vera").exists()
