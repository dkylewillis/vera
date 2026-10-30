"""Loopback agent service: auth, policy, and MCP round trip."""

from __future__ import annotations

import json
import socket
from pathlib import Path

import httpx
import pytest

from helpers.pdfs import make_pdf, make_topic_pdf
from vera_ingest import convert
from vera_mcp.access_policy import LOCAL_AGENT_DISCLOSURE, AccessPolicy
from vera_mcp.service import main_service, running_service, serve, warm_default_embedder


@pytest.fixture
def library(tmp_path: Path) -> dict[str, Path]:
    root = tmp_path / "approved"
    root.mkdir()
    pdf = root / "manual.pdf"
    archive = root / "manual.vera"
    make_pdf(pdf)
    convert(str(pdf), str(archive), model="hashing")
    outside = tmp_path / "outside"
    outside.mkdir()
    secret_pdf = outside / "secret.pdf"
    make_topic_pdf(secret_pdf, "Confidential", "UNIQUE_SENTINEL_PHRASE_XYZ stays outside.")
    secret = outside / "secret.vera"
    convert(str(secret_pdf), str(secret), model="hashing")
    policy = AccessPolicy.from_mapping(
        {"library_roots": [str(root)], "disclosure": LOCAL_AGENT_DISCLOSURE}
    )
    return {"root": root, "archive": archive, "secret": secret, "policy": policy}


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _tool_payload(result: object) -> object:
    text = ""
    for block in getattr(result, "content", None) or []:
        piece = getattr(block, "text", None)
        if piece:
            text = piece
            break
    if text:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"text": text, "isError": bool(getattr(result, "isError", False))}
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured.get("result", structured)
    return {"isError": bool(getattr(result, "isError", False))}


@pytest.mark.anyio
async def test_healthz_auth_host_and_origin(library: dict[str, Path], tmp_path: Path) -> None:
    port = _free_port()
    token = "service-token"
    state = tmp_path / "state.json"
    url = f"http://127.0.0.1:{port}"
    with running_service(library["policy"], port=port, token=token, state_file=state):
        assert state.is_file()
        payload = json.loads(state.read_text(encoding="utf-8"))
        assert payload["url"] == f"{url}/mcp"
        assert payload["pid"]
        assert payload["version"]
        assert "token" not in payload

        async with httpx.AsyncClient(timeout=10) as client:
            health = await client.get(f"{url}/healthz")
            assert health.status_code == 200
            assert health.json()["ok"] is True
            assert health.json()["version"] == payload["version"]

            missing = await client.post(f"{url}/mcp")
            assert missing.status_code == 401
            wrong = await client.post(f"{url}/mcp", headers={"Authorization": "Bearer nope"})
            assert wrong.status_code == 401
            origin = await client.get(f"{url}/healthz", headers={"Origin": "http://evil.example"})
            assert origin.status_code == 403
            bad_host = await client.get(
                f"{url}/healthz",
                headers={"Host": "evil.example"},
            )
            assert bad_host.status_code == 421
    assert not state.exists()


@pytest.mark.anyio
async def test_mcp_round_trip_allows_library_and_denies_outside(library: dict[str, Path]) -> None:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    port = _free_port()
    token = "round-trip-token"
    url = f"http://127.0.0.1:{port}/mcp"
    headers = {"Authorization": f"Bearer {token}"}
    with running_service(library["policy"], port=port, token=token):
        async with httpx.AsyncClient(headers=headers, timeout=httpx.Timeout(30.0, read=60.0)) as http_client:
            client_streams = streamable_http_client(url, http_client=http_client)
            async with client_streams as (read, write, _get_session_id):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    info = _tool_payload(await session.call_tool("vera_library_info", {}))
                    assert isinstance(info, dict)
                    assert str(library["root"].resolve()) in info["library_roots"]
                    assert info["disclosure"] == LOCAL_AGENT_DISCLOSURE

                    search = _tool_payload(
                        await session.call_tool(
                            "vera_corpus_search",
                            {
                                "directory": str(library["root"]),
                                "query": "restaurant",
                                "mode": "keyword",
                                "top_k": 3,
                                "output": "compact",
                            },
                        )
                    )
                    assert isinstance(search, dict)
                    chunk_id = search["results"][0]["chunk_id"]
                    chunk = _tool_payload(
                        await session.call_tool(
                            "vera_get_chunk",
                            {"file": str(library["archive"]), "chunk_id": chunk_id},
                        )
                    )
                    assert isinstance(chunk, dict)
                    assert chunk["ok"] is True
                    assert chunk["chunk_id"] == chunk_id

                    denied_result = await session.call_tool(
                        "vera_search",
                        {
                            "file": str(library["secret"]),
                            "query": "UNIQUE_SENTINEL_PHRASE_XYZ",
                            "mode": "keyword",
                        },
                    )
                    denied = _tool_payload(denied_result)
                    denied_text = json.dumps(denied)
                    assert getattr(denied_result, "isError", False) or "denied" in denied_text.lower()
                    assert "UNIQUE_SENTINEL" not in denied_text


def test_bind_failure_is_reported(library: dict[str, Path], capsys: pytest.CaptureFixture[str]) -> None:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    try:
        code = serve(library["policy"], port=port, token="token")
    finally:
        sock.close()
    assert code == 1
    assert "could not bind" in capsys.readouterr().err


def test_main_service_requires_policy_and_token(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.delenv("VERA_SERVICE_TOKEN", raising=False)
    monkeypatch.setenv("VERA_AUTO_INSTALL_SEMANTIC_DEPS", "1")
    assert main_service([]) == 2
    assert "VERA_SERVICE_TOKEN" in capsys.readouterr().err
    assert "VERA_AUTO_INSTALL_SEMANTIC_DEPS" not in __import__("os").environ

    monkeypatch.setenv("VERA_SERVICE_TOKEN", "token")
    assert main_service(["--policy", str(tmp_path / "missing.json")]) == 2
    assert "missing" in capsys.readouterr().err


def test_warm_skips_unavailable_embedder(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import vera_doc.embeddings as embeddings

    def boom(_spec: str) -> None:
        raise RuntimeError("no model")

    monkeypatch.setattr(embeddings, "get_embedder", boom)
    warm_default_embedder()
    assert "warm-up skipped" in capsys.readouterr().err
