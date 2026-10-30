"""Stdio MCP forwarder for the loopback VERA agent service.

Agents that can only launch a subprocess run::

    python -m vera_mcp.connect --connect-file connect.json

``connect.json`` is ``{"url": "http://127.0.0.1:PORT/mcp", "token": "..."}``.
The forwarder speaks MCP on stdin/stdout and sends every tool and resource
request to that service. If the service is down, it exits with a message and
does not start an unrestricted local server.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

DOWN_MESSAGE = "Start VERA Desktop and enable Agent access."


def load_connect_file(path: str | Path) -> tuple[str, str]:
    """Return ``(url, token)`` or raise ``ValueError`` with a user-facing message."""
    connect_path = Path(path)
    try:
        raw = json.loads(connect_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read the VERA connect file. {DOWN_MESSAGE}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"VERA connect file must be a JSON object. {DOWN_MESSAGE}")
    url = raw.get("url")
    token = raw.get("token")
    if not isinstance(url, str) or not _is_loopback_http(url):
        raise ValueError(f"VERA connect file must point at a loopback HTTP service. {DOWN_MESSAGE}")
    if not isinstance(token, str) or not token.strip():
        raise ValueError(f"VERA connect file is missing a token. {DOWN_MESSAGE}")
    return url, token.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vera-mcp-connect")
    parser.add_argument("--connect-file", default="")
    args = parser.parse_args(argv)
    if not str(args.connect_file).strip():
        print(f"VERA connect requires --connect-file. {DOWN_MESSAGE}", file=sys.stderr, flush=True)
        return 2
    try:
        url, token = load_connect_file(args.connect_file)
    except ValueError as exc:
        print(str(exc), file=sys.stderr, flush=True)
        return 2
    try:
        return asyncio.run(_forward(url, token))
    except KeyboardInterrupt:
        return 0


async def _forward(url: str, token: str) -> int:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    from mcp.server.lowlevel.helper_types import ReadResourceContents
    from mcp.server.stdio import stdio_server
    from mcp.shared._httpx_utils import create_mcp_http_client

    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with create_mcp_http_client(headers=headers) as http_client:
            async with streamable_http_client(url, http_client=http_client) as (read, write, _session_id):
                async with ClientSession(read, write) as remote:
                    await remote.initialize()
                    proxy = _proxy_server(remote, ReadResourceContents)
                    async with stdio_server() as (stdin, stdout):
                        await proxy.run(
                            stdin,
                            stdout,
                            proxy.create_initialization_options(),
                        )
    except BaseException as exc:
        if not _is_connect_failure(exc):
            raise
        print(f"{DOWN_MESSAGE} ({exc.__class__.__name__})", file=sys.stderr, flush=True)
        return 2
    return 0


def _is_connect_failure(exc: BaseException) -> bool:
    """True when the service could not be reached, including wrapped task-group errors."""
    if isinstance(exc, (KeyboardInterrupt, SystemExit)):
        return False
    if isinstance(exc, (httpx.HTTPError, OSError, ConnectionError)):
        return True
    nested = getattr(exc, "exceptions", None)
    if isinstance(nested, tuple) and nested:
        return all(_is_connect_failure(item) for item in nested)
    return False


def _proxy_server(remote: Any, read_resource_contents: type[Any]) -> Any:
    from mcp.server.lowlevel.server import Server

    server = Server("vera")

    @server.list_tools()
    async def _list_tools() -> list[Any]:
        listed = await remote.list_tools()
        return list(listed.tools)

    @server.call_tool(validate_input=False)
    async def _call_tool(name: str, arguments: dict[str, Any]) -> Any:
        return await remote.call_tool(name, arguments)

    @server.list_resources()
    async def _list_resources() -> list[Any]:
        listed = await remote.list_resources()
        return list(listed.resources)

    @server.read_resource()
    async def _read_resource(uri: Any) -> list[Any]:
        listed = await remote.read_resource(uri)
        contents: list[Any] = []
        for block in listed.contents:
            mime = getattr(block, "mimeType", None)
            meta = getattr(block, "meta", None)
            if isinstance(meta, dict) or meta is None:
                meta_dict = meta
            else:
                meta_dict = dict(meta)
            text = getattr(block, "text", None)
            blob = getattr(block, "blob", None)
            if text is not None:
                contents.append(read_resource_contents(content=text, mime_type=mime, meta=meta_dict))
            elif blob is not None:
                contents.append(
                    read_resource_contents(
                        content=base64.b64decode(blob),
                        mime_type=mime,
                        meta=meta_dict,
                    )
                )
        return contents

    return server


def _is_loopback_http(url: str) -> bool:
    parsed = urlparse(url.strip())
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        return False
    if parsed.username or parsed.password:
        return False
    return parsed.port is not None


if __name__ == "__main__":
    raise SystemExit(main())
