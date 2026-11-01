"""Convert small Office files generated with the same libraries the pipeline uses."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from docx import Document
from docx.oxml import parse_xml
from openpyxl import Workbook
from pptx import Presentation
from pptx.util import Inches

from vera_doc import VeraDocument
from vera_ingest.convert import batch_convert, convert
from vera_ingest.formats import resolve_ingest_parser
from vera_ingest.types import IngestRequest
from vera_ingest.viewer import format_search_context, get_viewer_preview
from vera_ingest_ooxml import ensure_registered
from vera_ingest_ooxml.pipeline import ooxml_pipeline

# 1x1 PNG.
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


def _word(path: Path) -> None:
    document = Document()
    document.add_heading("Detention design", level=1)
    document.add_paragraph("Ponds hold stormwater.")
    document.add_paragraph("Check the outlet.", style="List Bullet")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Item"
    table.cell(0, 1).text = "Size"
    table.cell(1, 0).text = "Pond"
    table.cell(1, 1).text = "Large"
    document.save(path)


def _deck(path: Path) -> None:
    presentation = Presentation()
    blank = presentation.slide_layouts[6]
    first = presentation.slides.add_slide(presentation.slide_layouts[0])
    first.shapes.title.text = "Site plan"
    first.placeholders[1].text = "Roundabout approach"
    notes = first.notes_slide.notes_text_frame
    notes.text = "Mention the culvert."
    second = presentation.slides.add_slide(blank)
    image = path.with_suffix(".png")
    image.write_bytes(_PNG)
    second.shapes.add_picture(str(image), Inches(1), Inches(1), Inches(1), Inches(1))
    presentation.save(path)


def _workbook(path: Path) -> None:
    book = Workbook()
    sheet = book.active
    sheet.title = "Budget"
    sheet["A1"] = "Item"
    sheet["B1"] = "Qty"
    sheet["A2"] = "Widget"
    sheet["B2"] = 2
    sheet["A3"] = "Bolt"
    sheet["B3"] = 5
    sheet["A4"] = "Total"
    sheet["B4"] = "=B2+B3"
    empty = book.create_sheet("Empty")
    empty["A1"] = None
    book.save(path)


def test_word_table_with_misaligned_merged_cells_keeps_text(tmp_path: Path) -> None:
    source = tmp_path / "zones.docx"
    document = Document()
    document.add_paragraph("Zoning districts")
    grid = "".join('<w:gridCol w:w="100"/>' for _ in range(14))
    table_xml = f"""
        <w:tbl xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:tblGrid>{grid}</w:tblGrid>
          <w:tr>
            <w:tc>
              <w:tcPr><w:gridSpan w:val="10"/></w:tcPr>
              <w:p><w:r><w:t>District</w:t></w:r></w:p>
            </w:tc>
            <w:tc>
              <w:tcPr><w:gridSpan w:val="4"/></w:tcPr>
              <w:p><w:r><w:t>Setback</w:t></w:r></w:p>
            </w:tc>
          </w:tr>
          <w:tr>
            <w:tc>
              <w:tcPr><w:gridSpan w:val="13"/></w:tcPr>
              <w:p><w:r><w:t>R-1</w:t></w:r></w:p>
            </w:tc>
            <w:tc>
              <w:tcPr><w:vMerge w:val="continue"/><w:gridSpan w:val="1"/></w:tcPr>
              <w:p><w:r><w:t>20 ft</w:t></w:r></w:p>
            </w:tc>
          </w:tr>
        </w:tbl>
        """
    document.element.body.append(parse_xml(table_xml))
    document.save(source)
    broken = Document(str(source)).tables[0]
    with pytest.raises(ValueError, match="grid_offset"):
        _ = broken.rows[1].cells

    result = ooxml_pipeline(str(source), IngestRequest())
    tables = [block.text for block in result.blocks if block.block_type == "table"]
    assert len(tables) == 1
    assert "District" in tables[0]
    assert "Setback" in tables[0]
    assert "R-1" in tables[0]
    assert "20 ft" in tables[0]


def _word_with_picture(path: Path) -> None:
    document = Document()
    document.add_heading("Site plan", level=1)
    document.add_paragraph("The pond sits north of the lot.")
    image = path.with_suffix(".png")
    image.write_bytes(_PNG)
    document.add_picture(str(image))
    document.inline_shapes[0]._inline.docPr.set("descr", "Pond [north] layout")
    document.add_paragraph("Outlet details follow.")
    document.save(path)


def test_word_pictures_become_figures_linked_from_the_preview(tmp_path: Path) -> None:
    source = tmp_path / "plan.docx"
    _word_with_picture(source)
    result = ooxml_pipeline(str(source), IngestRequest())
    assert result.warnings == []
    image = next(block for block in result.blocks if block.block_type == "image")
    assert image.image_bytes == _PNG
    assert image.image_ext == "png"
    lines = result.viewer_preview.data.decode("utf-8").splitlines()
    region = image.regions[0]
    assert region["kind"] == "text_span"
    assert lines[region["start"]["line"] - 1] == (
        f"![Pond \\[north\\] layout](vera-figure:{image.block_id})"
    )
    assert any(image.block_id in chunk.block_ids for chunk in result.chunks)

    output = tmp_path / "plan.vera"
    convert(str(source), str(output), model="hashing")
    with VeraDocument.open(str(output)) as document:
        figures = document.attachment_metadata(None, where={"role": "figure"})
        assert [item["id"] for item in figures] == [f"image_{image.block_id}"]
        assert figures[0]["media_type"] == "image/png"
        hit = document.search("pond north of the lot", mode="keyword", top_k=1)[0]
        assert any(ref.role == "figure" for ref in hit.record.attachments)


def test_word_preview_lines_match_heading_span(tmp_path: Path) -> None:
    source = tmp_path / "memo.docx"
    _word(source)
    result = ooxml_pipeline(str(source), IngestRequest())
    preview = result.viewer_preview
    assert preview is not None
    assert preview.media_type == "text/markdown"
    lines = preview.data.decode("utf-8").splitlines()
    heading = next(block for block in result.blocks if block.block_type == "heading")
    region = heading.regions[0]
    assert region["kind"] == "text_span"
    assert lines[region["start"]["line"] - 1] == "# Detention design"
    assert any(block.block_type == "table" and "Pond" in block.text for block in result.blocks)
    assert any(block.block_type == "list" for block in result.blocks)
    assert result.chunks


def test_slides_include_notes_and_a_picture(tmp_path: Path) -> None:
    source = tmp_path / "deck.pptx"
    _deck(source)
    result = ooxml_pipeline(str(source), IngestRequest())
    assert [page.page_number for page in result.pages] == [1, 2]
    assert any(block.block_type == "notes" and "culvert" in block.text for block in result.blocks)
    assert any(block.block_type == "image" and block.image_bytes for block in result.blocks)
    notes = next(block for block in result.blocks if block.block_type == "notes")
    assert notes.regions[0]["kind"] == "slide"
    assert notes.regions[0]["slide"] == 1
    assert result.chunks[0].metadata["citation_label"] == "slide 1"
    preview = json.loads(result.viewer_preview.data)
    assert preview["slides"][0]["blocks"][0]["block_id"].startswith("block_")


def test_sheet_repeats_header_and_keeps_formula_text(tmp_path: Path) -> None:
    source = tmp_path / "budget.xlsx"
    _workbook(source)
    result = ooxml_pipeline(str(source), IngestRequest(pipeline_options={"rows_per_chunk": 2}))
    tables = [block for block in result.blocks if block.block_type == "table"]
    assert len(tables) == 2
    assert all(block.text.splitlines()[0].startswith("| Item |") for block in tables)
    assert tables[0].regions[0]["range"] == "A1:B3"
    assert tables[0].regions[0]["sheet"] == "Budget"
    assert tables[1].regions[0]["range"] == "A1:B4"
    joined = "\n".join(block.text for block in tables)
    assert "Widget" in joined
    assert "=B2+B3" in joined or "7" in joined
    assert result.chunks[0].metadata["citation_label"] == "Budget!A1:B3"
    preview = json.loads(result.viewer_preview.data)
    assert preview["sheets"][0]["name"] == "Budget"
    assert all(sheet["name"] != "Empty" for sheet in preview["sheets"])
    context = format_search_context(
        [{"text": result.chunks[0].text, "citation_label": "Budget!A1:B3", "heading_path": "Budget"}]
    )
    assert "Budget!A1:B3" in context
    assert "p. 1" not in context


def test_empty_workbook_has_no_chunks(tmp_path: Path) -> None:
    source = tmp_path / "empty.xlsx"
    book = Workbook()
    book.active.title = "Blank"
    book.save(source)
    result = ooxml_pipeline(str(source), IngestRequest())
    assert result.chunks == []
    with pytest.raises(ValueError, match="No searchable text"):
        convert(str(source), str(tmp_path / "empty.vera"), model="hashing")


def test_convert_stores_preview_and_original(tmp_path: Path) -> None:
    ensure_registered()
    source = tmp_path / "memo.docx"
    _word(source)
    target = tmp_path / "memo.vera"
    assert resolve_ingest_parser(source) == "ooxml"
    convert(str(source), str(target), model="hashing")
    with VeraDocument.open(target) as document:
        preview = get_viewer_preview(document)
        assert preview is not None
        assert preview.media_type == "text/markdown"
        assert "Detention design" in preview.data.decode("utf-8")
        assert document.metadata["source_mime_type"].endswith("wordprocessingml.document")
        assert document.metadata["parser_name"] == "ooxml"
        assert "ingest_warnings" not in document.metadata


def test_header_and_content_control_are_notes_not_warnings(tmp_path: Path) -> None:
    source = tmp_path / "zones.docx"
    document = Document()
    document.add_paragraph("Zoning districts")
    document.sections[0].header.paragraphs[0].text = "CONFIDENTIAL"
    document.element.body.append(
        parse_xml(
            """
            <w:sdt xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
              <w:sdtContent>
                <w:p><w:r><w:t>Inside control</w:t></w:r></w:p>
              </w:sdtContent>
            </w:sdt>
            """
        )
    )
    document.save(source)
    result = ooxml_pipeline(str(source), IngestRequest())
    assert result.warnings == []
    assert result.notes == [
        "Headers, footers, and content controls aren't included in search. "
        "VERA searches the main body text."
    ]
    assert any("Zoning districts" in block.text for block in result.blocks)
    assert all("Inside control" not in block.text for block in result.blocks)
    target = tmp_path / "zones.vera"
    convert(str(source), str(target), model="hashing")
    with VeraDocument.open(target) as stored:
        assert stored.metadata["ingest_notes"] == result.notes
        assert "ingest_warnings" not in stored.metadata


def test_unreadable_table_keeps_the_rest_of_the_document(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "memo.docx"
    _word(source)

    def boom(_table):
        raise ValueError("no `tc` element at grid_offset=13")

    monkeypatch.setattr("vera_ingest_ooxml.docx._table_rows", boom)
    result = ooxml_pipeline(str(source), IngestRequest())
    assert any(block.block_type == "paragraph" for block in result.blocks)
    assert any("1 table could not be read" in item and "grid_offset=13" in item for item in result.warnings)


def test_corrupt_docx_fails_and_a_noted_file_does_not(tmp_path: Path) -> None:
    folder = tmp_path / "library"
    folder.mkdir()
    good = folder / "memo.docx"
    document = Document()
    document.add_paragraph("Keep this")
    document.sections[0].header.paragraphs[0].text = "DRAFT"
    document.save(good)
    (folder / "bad.docx").write_bytes(b"not a zip")
    report = batch_convert(str(folder), model="hashing")
    assert report["converted"] == 1
    assert report["failed"] == 1
    assert report["warnings"] == []
    assert report["notes"][0]["input"].endswith("memo.docx")
    assert report["notes"][0]["notes"] == [
        "Headers and footers aren't included in search. VERA searches the main body text."
    ]
    assert "bad.docx" in report["errors"][0]["input"]
