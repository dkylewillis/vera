"""Tests for the MCP server tools (called in-process, no stdio transport)."""

import json

import pytest

from sdx import convert
from test_convert_search import make_pdf


@pytest.fixture(scope="module")
def sdx_file(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("mcp")
    pdf = tmp / "manual.pdf"
    out = tmp / "manual.sdx"
    make_pdf(pdf)
    convert(str(pdf), str(out), model="hashing", chunk_size=40, overlap=5)
    return out


@pytest.fixture(scope="module")
def server():
    from sdx.mcp_server import build_server

    return build_server()


@pytest.mark.anyio
async def test_tools_are_registered(server):
    tools = await server.list_tools()
    names = {t.name for t in tools}
    assert {"sdx_search", "sdx_inspect", "sdx_validate", "sdx_figures", "sdx_get_page"} <= names


@pytest.mark.anyio
async def test_search_tool_returns_citation_ready_results(server, sdx_file):
    result = await server.call_tool(
        "sdx_search",
        {"file": str(sdx_file), "query": "restaurant parking", "top_k": 2, "include_figures": True},
    )
    payload = _payload(result)
    assert payload["query"] == "restaurant parking"
    first = payload["results"][0]
    assert {"chunk_id", "score", "text", "page_start", "heading_path", "figures"} <= set(first)
    assert "parking" in first["text"].lower()


@pytest.mark.anyio
async def test_inspect_and_validate_tools(server, sdx_file):
    info = _payload(await server.call_tool("sdx_inspect", {"file": str(sdx_file)}))
    assert info["format_version"] == "0.1"
    assert info["pages"] == 2

    report = _payload(await server.call_tool("sdx_validate", {"file": str(sdx_file)}))
    assert report["ok"] is True


@pytest.mark.anyio
async def test_get_page_tool(server, sdx_file):
    page = _payload(await server.call_tool("sdx_get_page", {"file": str(sdx_file), "page_number": 2}))
    assert page["page_number"] == 2
    assert "detention" in page["text"].lower()

    missing = _payload(await server.call_tool("sdx_get_page", {"file": str(sdx_file), "page_number": 99}))
    assert "error" in missing


def _payload(call_result):
    """Extract the structured payload from a FastMCP call_tool result."""
    content, structured = call_result
    if structured is not None:
        return structured.get("result", structured)
    return json.loads(content[0].text)


@pytest.fixture
def anyio_backend():
    return "asyncio"
