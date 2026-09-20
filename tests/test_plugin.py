"""Exercise the packaged MCP command and the skill/tool documentation contract."""

import json
import os
import sys
from pathlib import Path

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from vera_doc import ChunkRecord, VeraDocument
from vera_mcp import build_server

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_plugin_components_and_documented_actions():
    manifest = json.loads((ROOT / ".codex-plugin/plugin.json").read_text())
    assert manifest["name"] == "vera"
    assert (ROOT / manifest["skills"] / "vera/SKILL.md").is_file()
    assert (ROOT / manifest["mcpServers"]).is_file()
    config = json.loads((ROOT / manifest["mcpServers"]).read_text())
    assert config["mcpServers"]["vera"]["env"]["VERA_AUTO_INSTALL_SEMANTIC_DEPS"] == "1"
    reference = (ROOT / "skills/vera/references/mcp-workflow.md").read_text()
    guide = (ROOT / "docs/plugin.md").read_text()
    for tool in await build_server().list_tools():
        assert tool.name in reference
        assert tool.name in guide


def _payload(result):
    assert not result.isError, result
    if result.structuredContent is not None:
        return result.structuredContent
    return json.loads(next(item.text for item in result.content if item.type == "text"))


@pytest.mark.anyio
async def test_configured_stdio_search_read_refine(tmp_path, monkeypatch):
    archive = tmp_path / "sample archive.vera"
    with VeraDocument.create(archive) as doc:
        doc.add(
            [
                ChunkRecord(
                    id="grid",
                    text="Detention is required for GRID projects.",
                    metadata={"company": "GRID", "source_filename": "manual.md"},
                ),
                ChunkRecord(
                    id="other",
                    text="Detention exemptions apply to OTHER projects.",
                    metadata={"company": "OTHER", "source_filename": "manual.md"},
                ),
            ]
        )
    original = archive.read_bytes()
    config = json.loads((ROOT / ".mcp.json").read_text())["mcpServers"]["vera"]
    assert config.get("env", {}).get("VERA_AUTO_INSTALL_SEMANTIC_DEPS") == "1"
    # Match an activated environment without replacing the configured executable.
    # Merge PATH into the configured env; StdioServerParameters rejects a duplicate env=.
    env = {
        **dict(config.get("env") or {}),
        "PATH": os.pathsep.join([str(Path(sys.executable).parent), os.environ["PATH"]]),
    }
    assert env["VERA_AUTO_INSTALL_SEMANTIC_DEPS"] == "1"
    # Windows resolves the executable using the parent's PATH before child env.
    monkeypatch.setenv("PATH", env["PATH"])
    params = StdioServerParameters(
        command=config["command"],
        args=list(config.get("args") or []),
        cwd=str(tmp_path),
        env=env,
    )
    with anyio.fail_after(30):
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = {tool.name for tool in (await session.list_tools()).tools}
                assert {
                    "vera_search",
                    "vera_get_chunk",
                    "vera_corpus_search",
                    "vera_show_sources",
                } <= tools
                broad = _payload(
                    await session.call_tool(
                        "vera_search",
                        {
                            "file": str(archive),
                            "query": "detention",
                            "top_k": 5,
                        },
                    )
                )
                assert {hit["chunk_id"] for hit in broad["results"]} == {"grid", "other"}
                hit = broad["results"][0]
                body = _payload(
                    await session.call_tool(
                        "vera_get_chunk",
                        {
                            "file": str(archive),
                            "chunk_id": hit["chunk_id"],
                        },
                    )
                )
                assert body["text"] == hit["text"]
                # Check UI resource metadata and private result data on the wire.
                resource = await session.read_resource("ui://vera/source-viewer-v1.html")
                assert resource.contents[0].mimeType == "text/html;profile=mcp-app"
                assert resource.contents[0].meta["ui"]["csp"]["connectDomains"] == []
                shown = await session.call_tool(
                    "vera_show_sources",
                    {
                        "sources": [
                            {"id": "C1", "file": str(archive), "chunk_id": hit["chunk_id"]}
                        ],
                    },
                )
                assert not shown.isError
                assert shown.meta["vera/view"]["mode"] == "launcher"
                assert shown.meta["vera/view"]["view"] is None
                assert shown.structuredContent["sources"][0]["text"] == hit["text"]
                assert shown.structuredContent["sources"][0]["id"] == "C1"
                refined = _payload(
                    await session.call_tool(
                        "vera_corpus_search",
                        {
                            "directory": str(tmp_path),
                            "query": "detention",
                            "mode": "keyword",
                            "where": {"company": "GRID"},
                            "context_chunks": 1,
                            "top_k": 1,
                        },
                    )
                )
                assert [r["chunk_id"] for r in refined["results"]] == ["grid"]
                assert Path(refined["results"][0]["file"]).resolve() == archive.resolve()
                missing = _payload(
                    await session.call_tool(
                        "vera_get_chunk",
                        {
                            "file": str(archive),
                            "chunk_id": "missing",
                        },
                    )
                )
                assert missing["ok"] is False
                assert "error" in missing
    assert archive.read_bytes() == original
