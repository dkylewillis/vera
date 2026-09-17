"""Bridge access-policy denials and fail-closed launch behavior."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from helpers.pdfs import make_pdf, make_topic_pdf
from vera_doc import VeraDocument
from vera_ingest import convert
from vera_mcp.access_policy import (
    POLICY_ENV,
    AccessDenied,
    AccessPolicy,
    canonicalize_path,
    load_policy_from_env,
)
from vera_mcp.source_viewer import SourceRef, read_chunk, source_view


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _payload(call_result):
    if hasattr(call_result, "structuredContent") and call_result.structuredContent is not None:
        structured = call_result.structuredContent
        return structured.get("result", structured) if isinstance(structured, dict) else structured
    if isinstance(call_result, tuple):
        content, structured = call_result
        if structured is not None:
            return structured.get("result", structured)
        return json.loads(content[0].text)
    if hasattr(call_result, "content"):
        return json.loads(call_result.content[0].text)
    return json.loads(call_result[0].text)


@pytest.fixture
def approved_library(tmp_path):
    library = tmp_path / "approved"
    library.mkdir()
    pdf = library / "manual.pdf"
    archive = library / "manual.vera"
    make_pdf(pdf)
    convert(str(pdf), str(archive), model="hashing")
    sibling = tmp_path / "approved-sibling"
    sibling.mkdir()
    sentinel_pdf = sibling / "secret.pdf"
    make_topic_pdf(
        sentinel_pdf,
        "Confidential",
        "UNIQUE_SENTINEL_PHRASE_XYZ must never leave the sibling library.",
    )
    sentinel = sibling / "secret.vera"
    convert(str(sentinel_pdf), str(sentinel), model="hashing")
    prefix_trap = tmp_path / "approved_extra"
    prefix_trap.mkdir()
    trap_pdf = prefix_trap / "trap.pdf"
    make_pdf(trap_pdf)
    trap = prefix_trap / "trap.vera"
    convert(str(trap_pdf), str(trap), model="hashing")
    return {
        "root": library,
        "archive": archive,
        "sibling": sibling,
        "sentinel": sentinel,
        "prefix_trap": trap,
        "policy": AccessPolicy(library_root=canonicalize_path(library, require_directory=True)),
    }


def test_policy_load_fail_closed(tmp_path, monkeypatch):
    monkeypatch.delenv(POLICY_ENV, raising=False)
    with pytest.raises(ValueError, match=POLICY_ENV):
        load_policy_from_env()

    missing = tmp_path / "missing.json"
    monkeypatch.setenv(POLICY_ENV, str(missing))
    with pytest.raises(ValueError, match="missing"):
        load_policy_from_env()

    bad = tmp_path / "bad.json"
    bad.write_text("{not-json", encoding="utf-8")
    monkeypatch.setenv(POLICY_ENV, str(bad))
    with pytest.raises(ValueError, match="JSON"):
        load_policy_from_env()

    empty = tmp_path / "empty.json"
    empty.write_text("{}", encoding="utf-8")
    monkeypatch.setenv(POLICY_ENV, str(empty))
    with pytest.raises(ValueError, match="library_root"):
        load_policy_from_env()


def test_policy_from_file_round_trip(approved_library, tmp_path):
    path = tmp_path / "policy.json"
    path.write_text(
        json.dumps({"library_root": str(approved_library["root"]), "max_top_k": 5}),
        encoding="utf-8",
    )
    policy = AccessPolicy.load(path)
    assert policy.library_root == approved_library["policy"].library_root
    assert policy.max_top_k == 5
    assert policy.clamp_top_k(99) == 5


def test_denies_outside_sibling_prefix_and_traversal(approved_library):
    policy = approved_library["policy"]
    with pytest.raises(AccessDenied):
        policy.check_archive(approved_library["sentinel"])
    with pytest.raises(AccessDenied):
        policy.check_archive(approved_library["prefix_trap"])
    with pytest.raises(AccessDenied):
        policy.check_archive(approved_library["root"] / ".." / "approved-sibling" / "secret.vera")
    with pytest.raises(AccessDenied):
        policy.check_library_root(approved_library["sibling"])
    assert (
        policy.check_archive(approved_library["archive"])
        == Path(approved_library["archive"]).resolve()
    )


@pytest.mark.skipif(sys.platform != "win32", reason="UNC rejection is Windows-oriented")
def test_rejects_unc_paths(approved_library):
    policy = approved_library["policy"]
    with pytest.raises(AccessDenied):
        policy.check_archive(r"\\server\share\manual.vera")


def _first_chunk(archive: Path) -> str:
    with VeraDocument.open(archive) as doc:
        return doc.search(text="restaurant", top_k=1)[0].record.id


def test_viewer_and_tools_respect_policy(approved_library):
    policy = approved_library["policy"]
    with pytest.raises(AccessDenied):
        read_chunk(
            SourceRef(file=str(approved_library["sentinel"]), chunk_id="chunk_0001"),
            policy=policy,
        )
    with pytest.raises(AccessDenied):
        source_view(
            SourceRef(file=str(approved_library["sentinel"]), chunk_id="chunk_0001"),
            policy=policy,
        )

    ok = read_chunk(
        SourceRef(
            file=str(approved_library["archive"]),
            chunk_id=_first_chunk(approved_library["archive"]),
        ),
        policy=policy,
    )
    assert ok["chunk_id"]


@pytest.mark.anyio
async def test_bridge_server_omits_validate_and_denies_outside(approved_library):
    from vera_mcp import build_server

    policy = approved_library["policy"]
    server = build_server(policy=policy)
    names = {tool.name for tool in await server.list_tools()}
    assert "vera_library_info" in names
    assert "vera_validate" not in names
    assert "vera_search" in names

    info = _payload(await server.call_tool("vera_library_info", {}))
    assert info["library_root"] == str(policy.library_root)

    with pytest.raises(Exception, match="(?i)denied"):
        await server.call_tool(
            "vera_search",
            {
                "file": str(approved_library["sentinel"]),
                "query": "UNIQUE_SENTINEL_PHRASE_XYZ",
                "mode": "keyword",
            },
        )

    result = await server.call_tool(
        "vera_search",
        {
            "file": str(approved_library["archive"]),
            "query": "restaurant",
            "mode": "keyword",
            "top_k": 1,
        },
    )
    search_payload = _payload(result)
    assert search_payload["results"]


@pytest.mark.anyio
async def test_forged_viewer_request_denied(approved_library):
    from vera_mcp import build_server

    server = build_server(policy=approved_library["policy"])
    result = await server.call_tool(
        "vera_show_sources",
        {
            "sources": [
                {
                    "file": str(approved_library["sentinel"]),
                    "chunk_id": "chunk_0001",
                    "id": "C1",
                }
            ]
        },
    )
    payload = _payload(result)
    blob = json.dumps(payload)
    assert payload["sources"][0]["error"]
    assert "UNIQUE_SENTINEL" not in blob
    assert payload["sources"][0]["file"] == "(omitted)"


def test_main_bridge_fail_closed(monkeypatch, capsys):
    from vera_mcp import server as module

    monkeypatch.delenv(POLICY_ENV, raising=False)
    assert module.main_bridge() == 2
    err = capsys.readouterr().err
    assert POLICY_ENV in err


def test_junction_escape_denied(approved_library):
    if sys.platform != "win32":
        pytest.skip("junctions are a Windows concern for this PoC")
    import subprocess

    link = approved_library["root"] / "escape_link"
    target = approved_library["sibling"]
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        pytest.skip(f"could not create junction: {completed.stderr or completed.stdout}")
    policy = approved_library["policy"]
    escaped = link / "secret.vera"
    with pytest.raises(AccessDenied):
        policy.check_archive(escaped)
