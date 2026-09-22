"""Tests for the MCP server tools (called in-process, no stdio transport)."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from helpers.pdfs import make_pdf, make_structured_pdf
from vera_doc import ChunkRecord, VeraDocument
from vera_ingest import convert


def test_semantic_dependency_setup_is_opt_in(monkeypatch):
    from vera_mcp import server as module

    imported = []
    monkeypatch.delenv("VERA_AUTO_INSTALL_SEMANTIC_DEPS", raising=False)
    monkeypatch.setattr(module.importlib, "import_module", lambda name: imported.append(name))
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: pytest.fail("ran pip"))

    module.ensure_semantic_dependencies("hybrid")
    assert imported == []


def test_semantic_dependency_setup_installs_and_rechecks(monkeypatch):
    from vera_mcp import server as module

    attempts = []

    def import_module(name):
        attempts.append(name)
        if len(attempts) == 1:
            raise ImportError("missing")
        return object()

    commands = []
    monkeypatch.setenv("VERA_AUTO_INSTALL_SEMANTIC_DEPS", "1")
    monkeypatch.setattr(module.importlib, "import_module", import_module)
    monkeypatch.setattr(module.importlib, "invalidate_caches", lambda: None)
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda command, **kwargs: (
            commands.append((command, kwargs)) or SimpleNamespace(returncode=0)
        ),
    )

    module.ensure_semantic_dependencies("hybrid")

    assert attempts == ["sentence_transformers", "sentence_transformers"]
    assert commands == [
        (
            [module.sys.executable, "-m", "pip", "install", "sentence-transformers>=2.7"],
            {"check": False},
        )
    ]


def test_semantic_dependency_setup_skips_keyword_search(monkeypatch):
    from vera_mcp import server as module

    monkeypatch.setenv("VERA_AUTO_INSTALL_SEMANTIC_DEPS", "1")
    monkeypatch.setattr(
        module.importlib,
        "import_module",
        lambda name: pytest.fail("checked semantic dependencies"),
    )

    module.ensure_semantic_dependencies("keyword")


def test_mcp_server_starts_before_semantic_dependency_setup(monkeypatch):
    from vera_mcp import server as module

    monkeypatch.setattr(
        module,
        "ensure_semantic_dependencies",
        lambda mode: pytest.fail("installed before tool dispatch"),
    )
    started = []
    monkeypatch.setattr(
        module,
        "build_server",
        lambda policy=None: SimpleNamespace(run=lambda: started.append(True)),
    )

    assert module.main() == 0
    assert started == [True]


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
@pytest.mark.parametrize("corpus", [False, True])
async def test_compact_evidence_can_be_read_and_shown(server, vera_file, corpus):
    tool = "vera_corpus_search" if corpus else "vera_search"
    args = {"directory": str(vera_file.parent)} if corpus else {"file": str(vera_file)}
    args.update(query="restaurant parking", top_k=1, context_chunks=1)
    full = _payload(await server.call_tool(tool, args))
    compact = _payload(await server.call_tool(tool, {**args, "output": "compact"}))
    assert set(compact) == {"results"}
    hit = compact["results"][0]
    assert hit["text"] == full["results"][0]["text"]
    assert hit["page_start"] == full["results"][0]["page_start"]
    assert hit["file"] == str(vera_file.resolve())
    assert "score" not in hit
    for key in ("before_chunks", "after_chunks"):
        assert [c["text"] for c in hit.get(key, [])] == [
            c["text"] for c in full["results"][0].get(key, [])
        ]
    ref = {key: hit[key] for key in ("file", "chunk_id")}
    stored = _payload(await server.call_tool("vera_get_chunk", ref))
    assert stored["text"] == hit["text"]
    shown = await server.call_tool("vera_show_sources", {"sources": [ref]})
    assert "sources" in str(shown)
    assert len(json.dumps(compact)) < len(json.dumps(full))


@pytest.mark.anyio
async def test_compact_empty_corpus_preserves_coverage_warnings(server, monkeypatch):
    from vera_mcp.server import VeraCorpus

    class PartialCorpus:
        invalid_files = [{"file": "broken.vera", "error": "invalid archive"}]
        skipped_semantic_model_groups = [{"model": "unavailable", "reason": "missing"}]

        def search(self, **kwargs):
            return []

        def index_search_report(self):
            return {"used": True}

        def close(self):
            pass

    monkeypatch.setattr(VeraCorpus, "open", lambda *args, **kwargs: PartialCorpus())
    result = _payload(
        await server.call_tool(
            "vera_corpus_search", {"directory": ".", "query": "test", "output": "compact"}
        )
    )
    assert result["results"] == []
    assert result["warnings"]["skipped_files"] == PartialCorpus.invalid_files
    assert result["warnings"]["skipped_semantic_model_groups"] == (
        PartialCorpus.skipped_semantic_model_groups
    )


@pytest.mark.anyio
@pytest.mark.parametrize("tool", ["vera_search", "vera_corpus_search"])
@pytest.mark.parametrize("flag", ["pretty", "include_figures", "include_regions"])
async def test_compact_rejects_incompatible_options(server, tool, flag):
    args = {"file": "missing.vera"} if tool == "vera_search" else {"directory": "."}
    with pytest.raises(Exception, match='Use output="full"'):
        await server.call_tool(tool, {**args, "query": "test", "output": "compact", flag: True})


def test_compact_does_not_invent_missing_metadata():
    from vera_mcp.server import _compact_hit

    hit = _compact_hit({"chunk_id": "c1", "text": "body", "secret_tag": "omit"}, "a.vera")
    assert set(hit) == {"chunk_id", "text", "file"}


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
    assert "context" not in payload


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
async def test_search_tool_can_return_pretty_context(server, vera_file):
    result = await server.call_tool(
        "vera_search",
        {
            "file": str(vera_file),
            "query": "restaurant parking",
            "top_k": 1,
            "context_chunks": 1,
            "pretty": True,
        },
    )
    payload = _payload(result)
    assert payload["results"][0]["chunk_id"]
    assert "## Result 1" in payload["context"]
    assert "### Matching text" in payload["context"]
    assert "Source: manual.pdf (p. 1)" in payload["context"]
    assert payload["results"][0]["chunk_id"] not in payload["context"]


@pytest.mark.anyio
async def test_corpus_search_tool_can_return_pretty_context(server, vera_file):
    result = await server.call_tool(
        "vera_corpus_search",
        {
            "directory": str(vera_file.parent),
            "query": "restaurant parking",
            "top_k": 1,
            "pretty": True,
        },
    )
    payload = _payload(result)
    assert payload["results"][0]["file"] == str(vera_file)
    assert f"Archive: {vera_file}" in payload["context"]
    assert "Source: manual.pdf (p. 1)" in payload["context"]


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
        assert schema["properties"]["pretty"]["default"] is False


@pytest.fixture
def anyio_backend():
    return "asyncio"
