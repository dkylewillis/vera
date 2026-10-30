"""Stdio forwarder to the loopback agent service."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from helpers.pdfs import make_pdf
from vera_ingest import convert
from vera_mcp.access_policy import LOCAL_AGENT_DISCLOSURE, AccessPolicy
from vera_mcp.connect import DOWN_MESSAGE, main
from vera_mcp.service import running_service


@pytest.fixture
def library(tmp_path: Path) -> dict[str, object]:
    root = tmp_path / "approved"
    root.mkdir()
    pdf = root / "manual.pdf"
    archive = root / "manual.vera"
    make_pdf(pdf)
    convert(str(pdf), str(archive), model="hashing")
    policy = AccessPolicy.from_mapping(
        {"library_roots": [str(root)], "disclosure": LOCAL_AGENT_DISCLOSURE}
    )
    return {"root": root, "policy": policy}


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _tool_payload(result: object) -> object:
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if text:
            return json.loads(text)
    raise AssertionError("tool returned no JSON text")


@pytest.mark.anyio
async def test_forwards_tools_resources_and_calls(library: dict[str, object], tmp_path: Path) -> None:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    root = library["root"]
    assert isinstance(root, Path)
    port = _free_port()
    token = "connect-token"
    connect = tmp_path / "connect.json"
    connect.write_text(
        json.dumps({"url": f"http://127.0.0.1:{port}/mcp", "token": token}),
        encoding="utf-8",
    )
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "vera_mcp.connect", "--connect-file", str(connect)],
    )
    with running_service(library["policy"], port=port, token=token):  # type: ignore[arg-type]
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                show = next(tool for tool in tools.tools if tool.name == "vera_show_sources")
                meta = show.meta or {}
                assert meta.get("ui", {}).get("resourceUri")

                info = _tool_payload(await session.call_tool("vera_library_info", {}))
                assert isinstance(info, dict)
                assert str(root.resolve()) in info["library_roots"]

                resources = await session.list_resources()
                viewer = next(
                    resource for resource in resources.resources if "source-viewer" in str(resource.uri)
                )
                assert (viewer.meta or {}).get("ui")
                opened = await session.read_resource(viewer.uri)
                assert opened.contents
                assert "html" in (opened.contents[0].mimeType or "")


def test_service_down_fails_closed(tmp_path: Path) -> None:
    connect = tmp_path / "connect.json"
    connect.write_text(
        json.dumps({"url": "http://127.0.0.1:1/mcp", "token": "x"}),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [sys.executable, "-m", "vera_mcp.connect", "--connect-file", str(connect)],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 2
    assert DOWN_MESSAGE in completed.stderr
    assert completed.stdout == ""


def test_connect_file_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    assert DOWN_MESSAGE in capsys.readouterr().err

    missing = tmp_path / "missing.json"
    assert main(["--connect-file", str(missing)]) == 2
    assert DOWN_MESSAGE in capsys.readouterr().err

    remote = tmp_path / "remote.json"
    remote.write_text(
        json.dumps({"url": "https://example.com/mcp", "token": "secret-token"}),
        encoding="utf-8",
    )
    assert main(["--connect-file", str(remote)]) == 2
    err = capsys.readouterr().err
    assert "loopback" in err
    assert "secret-token" not in err
