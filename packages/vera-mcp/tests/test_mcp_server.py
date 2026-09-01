"""Tests for the MCP server tools (called in-process, no stdio transport)."""

import json
from pathlib import Path

import pytest

from helpers.pdfs import make_pdf, make_structured_pdf
from vera_doc import ChunkRecord, VeraDocument
from vera_ingest import convert


@pytest.fixture(scope="module")
def vera_file(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("mcp")
    pdf = tmp / "manual.pdf"
    out = tmp / "manual.vera"
    make_pdf(pdf)
    convert(str(pdf), str(out), model="hashing")
    return out


@pytest.fixture(scope="module")
def server():
    from vera_mcp import build_server

    return build_server()


@pytest.mark.anyio
async def test_tools_are_registered(server):
    tools = await server.list_tools()
    names = {t.name for t in tools}
    assert {
        "vera_search",
        "vera_inspect",
        "vera_validate",
        "vera_figures",
        "vera_get_figure",
        "vera_get_page",
        "vera_get_chunk",
    } <= names


@pytest.mark.anyio
async def test_search_tool_returns_citation_ready_results(server, vera_file):
    result = await server.call_tool(
        "vera_search",
        {
            "file": str(vera_file),
            "query": "restaurant parking",
            "top_k": 2,
            "include_figures": True,
        },
    )
    payload = _payload(result)
    assert payload["query"] == "restaurant parking"
    first = payload["results"][0]
    assert {"chunk_id", "score", "text", "page_start", "heading_path", "figures"} <= set(first)
    assert "parking" in first["text"].lower()


@pytest.mark.anyio
async def test_search_tool_returns_context_chunks(server, vera_file):
    result = await server.call_tool(
        "vera_search",
        {"file": str(vera_file), "query": "restaurant parking", "top_k": 1, "context_chunks": 1},
    )
    payload = _payload(result)
    first = payload["results"][0]
    assert {"before_chunks", "after_chunks"} <= set(first)
    assert isinstance(first["before_chunks"], list)
    assert isinstance(first["after_chunks"], list)


@pytest.mark.anyio
async def test_inspect_and_validate_tools(server, vera_file):
    info = _payload(await server.call_tool("vera_inspect", {"file": str(vera_file)}))
    assert info["format_version"] == "0.2"
    assert info["pages"] == 2
    assert info["default_embedding_normalization"] == "l2"
    assert info["file"] == str(vera_file)
    assert Path(info["path"]).resolve() == vera_file.resolve()

    report = _payload(await server.call_tool("vera_validate", {"file": str(vera_file)}))
    assert report["ok"] is True
    assert report["file"] == str(vera_file)
    assert Path(report["path"]).resolve() == vera_file.resolve()
    assert set(report["counts"]) >= {"chunks", "embeddings", "fts_rows", "attachments"}


@pytest.mark.anyio
async def test_get_page_tool(server, vera_file):
    page = _payload(
        await server.call_tool("vera_get_page", {"file": str(vera_file), "page_number": 2})
    )
    assert page["page_number"] == 2
    assert "detention" in page["text"].lower()

    missing = _payload(
        await server.call_tool("vera_get_page", {"file": str(vera_file), "page_number": 99})
    )
    assert "error" in missing


@pytest.mark.anyio
async def test_search_tool_returns_regions(server, vera_file):
    result = await server.call_tool(
        "vera_search",
        {
            "file": str(vera_file),
            "query": "restaurant parking",
            "top_k": 1,
            "include_regions": True,
        },
    )
    first = _payload(result)["results"][0]
    assert "regions" in first
    assert first["regions"]
    region = first["regions"][0]
    assert {"block_id", "page_number", "bbox", "page_width", "page_height"} <= set(region)
    assert len(region["bbox"]) == 4


@pytest.mark.anyio
async def test_get_chunk_regions_tool(server, vera_file):
    search = _payload(
        await server.call_tool(
            "vera_search", {"file": str(vera_file), "query": "restaurant parking", "top_k": 1}
        )
    )
    chunk_id = search["results"][0]["chunk_id"]
    regions = _payload(
        await server.call_tool(
            "vera_get_chunk_regions", {"file": str(vera_file), "chunk_id": chunk_id}
        )
    )
    assert regions
    assert regions[0]["page_number"] == search["results"][0]["page_start"]


@pytest.mark.anyio
async def test_get_chunk_tool_round_trips_search(server, vera_file):
    search = _payload(
        await server.call_tool(
            "vera_search", {"file": str(vera_file), "query": "restaurant parking", "top_k": 1}
        )
    )
    hit = search["results"][0]
    payload = _payload(
        await server.call_tool(
            "vera_get_chunk", {"file": str(vera_file), "chunk_id": hit["chunk_id"]}
        )
    )
    assert payload["ok"] is True
    assert payload["chunk_id"] == hit["chunk_id"]
    assert payload["text"] == hit["text"]
    assert payload["file"] == str(vera_file)
    assert Path(payload["path"]).resolve() == vera_file.resolve()
    assert "score" not in payload
    assert "semantic_score" not in payload
    assert "keyword_score" not in payload
    for key in ("page_start", "page_end", "heading_path", "source_filename", "document_id"):
        assert payload.get(key) == hit.get(key)


@pytest.mark.anyio
async def test_get_chunk_missing_id_returns_error(server, vera_file):
    payload = _payload(
        await server.call_tool("vera_get_chunk", {"file": str(vera_file), "chunk_id": "chunk_zzzz"})
    )
    assert payload == {"ok": False, "error": "chunk not found: chunk_zzzz"}


@pytest.mark.anyio
async def test_get_chunk_locator_wins_over_chunk_metadata(server, tmp_path):
    out = tmp_path / "notes.vera"
    with VeraDocument.create(str(out)) as document:
        document.add(
            [
                ChunkRecord(
                    id="chunk_0001",
                    text="Ponds must detain the 25-year storm.",
                    metadata={
                        "file": "WRONG.vera",
                        "path": "/evil/path",
                        "ok": False,
                        "error": "spoofed",
                    },
                )
            ]
        )
    payload = _payload(
        await server.call_tool("vera_get_chunk", {"file": str(out), "chunk_id": "chunk_0001"})
    )
    assert payload["ok"] is True
    assert payload["file"] == str(out)
    assert Path(payload["path"]).resolve() == out.resolve()
    assert "error" not in payload
    assert payload["chunk_id"] == "chunk_0001"


def _payload(call_result):
    """Extract the structured payload from a FastMCP call_tool result."""
    if isinstance(call_result, tuple):
        content, structured = call_result
        if structured is not None:
            return structured.get("result", structured)
        return json.loads(content[0].text)
    return json.loads(call_result[0].text)


@pytest.fixture(scope="module")
def vera_file_with_figures(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("mcp-figures")
    pdf = tmp / "manual.pdf"
    out = tmp / "manual.vera"
    make_structured_pdf(pdf)
    convert(str(pdf), str(out), model="hashing")
    return out


def _tool_content(call_result):
    if isinstance(call_result, tuple):
        return call_result[0]
    return call_result


@pytest.mark.anyio
async def test_get_figure_returns_image_content(server, vera_file_with_figures):
    listed = _payload(await server.call_tool("vera_figures", {"file": str(vera_file_with_figures)}))
    assert listed
    asset_id = listed[0]["asset_id"]
    result = await server.call_tool(
        "vera_get_figure",
        {"file": str(vera_file_with_figures), "asset_id": asset_id},
    )
    content = _tool_content(result)
    types = {getattr(block, "type", None) for block in content}
    assert "image" in types
    assert "text" in types
    image = next(block for block in content if getattr(block, "type", None) == "image")
    assert image.mimeType.startswith("image/")
    assert image.data
    text = next(block for block in content if getattr(block, "type", None) == "text")
    metadata = json.loads(text.text)
    assert metadata["asset_id"] == asset_id
    assert "data" not in metadata


@pytest.mark.anyio
async def test_get_figure_missing_asset_returns_error(server, vera_file_with_figures):
    payload = _payload(
        await server.call_tool(
            "vera_get_figure",
            {"file": str(vera_file_with_figures), "asset_id": "image_block_missing"},
        )
    )
    assert payload == {"error": "Figure image_block_missing not found"}


@pytest.mark.anyio
async def test_get_figure_rejects_non_figure_attachment(server, vera_file_with_figures):
    from vera_doc.document import VeraDocument

    doc = VeraDocument.open(str(vera_file_with_figures))
    try:
        source_id = str(doc.metadata["source_attachment_id"])
    finally:
        doc.close()
    payload = _payload(
        await server.call_tool(
            "vera_get_figure",
            {"file": str(vera_file_with_figures), "asset_id": source_id},
        )
    )
    assert payload == {"error": f"Figure {source_id} not found"}


@pytest.mark.anyio
async def test_search_tools_default_top_k_matches_cli(server):
    tools = {tool.name: tool for tool in await server.list_tools()}
    for name in ("vera_search", "vera_corpus_search"):
        schema = tools[name].inputSchema
        assert schema["properties"]["top_k"]["default"] == 10


@pytest.fixture
def anyio_backend():
    return "asyncio"
