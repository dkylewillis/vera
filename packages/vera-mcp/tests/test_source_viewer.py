"""Source rendering contracts, including archive fallbacks and MCP resource wiring."""

import base64
import json

import pymupdf
import pytest

from vera_doc import AttachmentRecord, ChunkRecord, VeraDocument
from vera_ingest import convert
from vera_mcp import build_server
from vera_mcp.source_viewer import RESOURCE_URI, SourceRef, _pdf_view, source_view


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def source_archives(tmp_path):
    pdf_path = tmp_path / "manual.pdf"
    pdf = pymupdf.open()
    for title in ("Capacity expansion", "Project exceptions"):
        page = pdf.new_page(width=600, height=760)
        page.insert_text((60, 90), title, fontsize=24)
        page.insert_text(
            (60, 140), "GRID plans capacity expansion with a new substation.", fontsize=12
        )
    pdf.save(pdf_path)
    pdf.close()
    archive = tmp_path / "manual.vera"
    convert(str(pdf_path), str(archive), model="hashing")
    md_path = tmp_path / "notes.md"
    md_path.write_text(
        "# Research notes\n\nCapacity expansion requires approval.\n\n"
        "<script>window.injected = true</script>\n",
        encoding="utf-8",
    )
    md_archive = tmp_path / "notes.vera"
    convert(str(md_path), str(md_archive), model="hashing")
    refs = []
    for path in (archive, md_archive):
        with VeraDocument.open(path) as doc:
            hit = doc.search(text="capacity expansion", top_k=1)[0]
            refs.append(SourceRef(file=str(path), chunk_id=hit.record.id))
    return refs


def test_pdf_preview_has_normalized_highlights_and_preserves_archive(source_archives):
    ref = source_archives[0]
    before = open(ref.file, "rb").read()
    view = source_view(ref)
    assert view["kind"] == "pdf"
    assert view["page_count"] == 2
    assert view["boxes"]
    assert base64.b64decode(view["image"].split(",")[1]).startswith(b"\x89PNG")
    assert all(0 <= n <= 1 for box in view["boxes"] for n in box)
    assert source_view(ref, 2)["page"] == 2
    assert open(ref.file, "rb").read() == before


def test_markdown_has_numbered_source_and_line_spans(source_archives):
    view = source_view(source_archives[1])
    assert view["kind"] == "markdown"
    assert view["spans"] and view["line_start"] == 1
    assert any("<script>" in line for line in view["lines"])
    with pytest.raises(ValueError, match="section"):
        source_view(source_archives[1], 99)


def test_missing_original_is_text_fallback(tmp_path):
    path = tmp_path / "bare.vera"
    with VeraDocument.create(path) as doc:
        doc.add([ChunkRecord(id="one", text="A stored passage")])
    view = source_view(SourceRef(file=str(path), chunk_id="one"))
    assert view["kind"] == "text"
    assert "not stored" in view["notice"]
    assert view["text"] == "A stored passage"


def test_invalid_locator_and_missing_chunk(source_archives):
    with pytest.raises(ValueError, match="absolute"):
        source_view(SourceRef(file="relative.vera", chunk_id="one"))
    with pytest.raises(ValueError, match="Chunk not found"):
        source_view(SourceRef(file=source_archives[0].file, chunk_id="missing"))
    with pytest.raises(ValueError, match="positive"):
        source_view(source_archives[0], -1)
    bad_page = source_view(source_archives[0], 999)
    assert bad_page["kind"] == "text" and "Page must be" in bad_page["notice"]


def test_oversized_original_falls_back(source_archives, monkeypatch):
    monkeypatch.setattr("vera_mcp.source_viewer.MAX_SOURCE_BYTES", 10)
    view = source_view(source_archives[0])
    assert view["kind"] == "text" and "preview limit" in view["notice"]


def test_rotated_pdf_does_not_claim_verified_highlights(tmp_path):
    path = tmp_path / "rotated.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((60, 100), "Capacity expansion plans")
        page.set_rotation(90)
        pdf.save(path)
    out = tmp_path / "rotated.vera"
    convert(str(path), str(out), model="hashing")
    with VeraDocument.open(out) as doc:
        chunk = doc.search(text="capacity", top_k=1)[0].record
    view = source_view(SourceRef(file=str(out), chunk_id=chunk.id))
    assert view["kind"] == "pdf" and not view["boxes"]
    assert "rotated" in view["notice"]


@pytest.mark.anyio
async def test_ui_tool_metadata_resource_and_private_images(source_archives):
    server = build_server()
    tools = {tool.name: tool for tool in await server.list_tools()}
    assert tools["vera_show_sources"].meta["ui"]["resourceUri"] == RESOURCE_URI
    assert tools["vera_show_sources"].annotations.readOnlyHint is True
    assert tools["vera_source_page"].meta["ui"]["visibility"] == ["app"]
    resource = list(await server.read_resource(RESOURCE_URI))[0]
    assert resource.mime_type == "text/html;profile=mcp-app"
    assert "ui/initialize" in resource.content
    result = await server.call_tool(
        "vera_show_sources",
        {
            "sources": [
                {**r.model_dump(), "id": f"C{i}"} for i, r in enumerate(source_archives, 1)
            ],
        },
    )
    # A CallToolResult return is passed through by FastMCP.
    assert result.meta["vera/view"]["mode"] == "launcher"
    assert result.meta["vera/view"]["view"] is None
    assert result.meta["vera/view"]["selected"] is None
    assert len(result.structuredContent["sources"]) == 2
    assert [item["id"] for item in result.structuredContent["sources"]] == ["C1", "C2"]
    assert "data:image" not in json.dumps(result.structuredContent)
    page_result = await server.call_tool(
        "vera_source_page",
        {
            **source_archives[0].model_dump(),
            "page": 2,
        },
    )
    assert page_result.meta["vera/view"]["page"] == 2


def test_viewer_uses_vera_app_brand_tokens_and_icon():
    from importlib.resources import files
    from pathlib import Path

    html = files("vera_mcp").joinpath("ui/source-viewer.html").read_text(encoding="utf-8")
    app_root = Path(__file__).resolve().parents[2] / "vera-app" / "src" / "renderer"
    app_css = (app_root / "styles.css").read_text(encoding="utf-8")
    icon = (app_root / "components" / "VeraIcon.tsx").read_text(encoding="utf-8")
    for token in ("#2563eb", "#0e9f6e", "#def7ec", "#1f2430", 'Inter,"Segoe UI"'):
        assert token in html
        assert token.replace('Inter,"Segoe UI"', 'Inter, "Segoe UI"') in app_css
    assert "M7.25 9.25H9.55L12 15.15" in html
    assert "M7.25 9.25H9.55L12 15.15" in icon


@pytest.mark.anyio
async def test_partial_failure_and_empty_source_input(source_archives):
    server = build_server()
    bad = {"file": source_archives[0].file, "chunk_id": "missing"}
    result = await server.call_tool(
        "vera_show_sources",
        {
            "sources": [bad, source_archives[1].model_dump()],
        },
    )
    assert "error" in result.structuredContent["sources"][0]
    assert result.meta["vera/view"]["selected"] is None
    with pytest.raises(Exception, match="at least 1"):
        await server.call_tool("vera_show_sources", {"sources": []})


def test_pdf_coordinates_and_dimension_mismatch():
    with pymupdf.open() as pdf:
        pdf.new_page(width=600, height=800)
        source = AttachmentRecord(id="pdf", data=pdf.tobytes(), media_type="application/pdf")
    region = {"page_number": 1, "bbox": [60, 80, 180, 120], "page_width": 600, "page_height": 800}
    view = _pdf_view(source, [region], 1, 1)
    assert view["boxes"][0] == pytest.approx([0.1, 0.1, 0.2, 0.05])
    mismatch = _pdf_view(source, [{**region, "page_width": 900}], 1, 1)
    assert mismatch["boxes"] == []
    assert "No verified" in mismatch["notice"]


@pytest.mark.anyio
async def test_corrupt_archive_is_a_partial_failure(source_archives, tmp_path):
    corrupt = tmp_path / "corrupt.vera"
    corrupt.write_bytes(b"not an archive")
    result = await build_server().call_tool(
        "vera_show_sources",
        {
            "sources": [
                {"file": str(corrupt), "chunk_id": "one"},
                source_archives[1].model_dump(),
            ]
        },
    )
    assert "error" in result.structuredContent["sources"][0]
    assert result.meta["vera/view"]["view"] is None
