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


def test_symlink_escape_denied(approved_library):
    policy = approved_library["policy"]
    file_link = approved_library["root"] / "escape.vera"
    try:
        file_link.symlink_to(approved_library["sentinel"])
    except OSError as exc:
        pytest.skip(f"could not create symlink: {exc}")
    with pytest.raises(AccessDenied):
        policy.check_archive(file_link)

    dir_link = approved_library["root"] / "escape_dir"
    try:
        dir_link.symlink_to(approved_library["sibling"], target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"could not create directory symlink: {exc}")
    with pytest.raises(AccessDenied):
        policy.check_archive(dir_link / "secret.vera")


def test_rejects_unc_style_and_relative_paths(approved_library):
    policy = approved_library["policy"]
    with pytest.raises(AccessDenied, match="Network and device"):
        canonicalize_path("//server/share/library", require_directory=True)
    with pytest.raises(AccessDenied, match="absolute"):
        policy.check_archive("manual.vera")
    with pytest.raises(AccessDenied, match="empty"):
        canonicalize_path("  ", require_directory=False)
    with pytest.raises(AccessDenied, match=r"\.vera"):
        policy.check_archive(approved_library["root"] / "manual.pdf")
    missing = approved_library["root"] / "missing.vera"
    with pytest.raises(AccessDenied, match="not found"):
        policy.check_archive(missing)


def test_policy_mapping_validates_bounds_and_tools(approved_library):
    root = str(approved_library["root"])
    with pytest.raises(ValueError, match="max_top_k"):
        AccessPolicy.from_mapping({"library_root": root, "max_top_k": 0})
    with pytest.raises(ValueError, match="max_context_chunks"):
        AccessPolicy.from_mapping({"library_root": root, "max_context_chunks": -1})
    with pytest.raises(ValueError, match="non-empty list"):
        AccessPolicy.from_mapping({"library_root": root, "allowed_tools": []})
    with pytest.raises(ValueError, match="unsupported"):
        AccessPolicy.from_mapping({"library_root": root, "allowed_tools": ["vera_validate"]})
    policy = AccessPolicy.from_mapping(
        {"library_root": root, "max_context_chunks": 0, "allowed_tools": ["vera_search"]}
    )
    assert policy.max_context_chunks == 0
    assert policy.allowed_tools == frozenset({"vera_search"})
    with pytest.raises(AccessDenied):
        policy.require_tool("vera_corpus_search")


def test_clamps_reject_out_of_range_and_cap_high_values(approved_library):
    policy = AccessPolicy.from_mapping(
        {
            "library_root": str(approved_library["root"]),
            "max_top_k": 3,
            "max_context_chunks": 1,
        }
    )
    assert policy.clamp_top_k(1) == 1
    assert policy.clamp_top_k(99) == 3
    assert policy.clamp_context_chunks(0) == 0
    assert policy.clamp_context_chunks(8) == 1
    with pytest.raises(AccessDenied, match="top_k"):
        policy.clamp_top_k(0)
    with pytest.raises(AccessDenied, match="context_chunks"):
        policy.clamp_context_chunks(-1)


@pytest.mark.anyio
async def test_bridge_search_clamps_and_omits_disallowed_tools(approved_library):
    from vera_mcp import build_server

    policy = AccessPolicy.from_mapping(
        {
            "library_root": str(approved_library["root"]),
            "max_top_k": 1,
            "allowed_tools": ["vera_library_info", "vera_search"],
        }
    )
    server = build_server(policy=policy)
    names = {tool.name for tool in await server.list_tools()}
    assert names == {"vera_library_info", "vera_search"}

    with pytest.raises(Exception, match="(?i)denied|top_k"):
        await server.call_tool(
            "vera_search",
            {
                "file": str(approved_library["archive"]),
                "query": "restaurant",
                "mode": "keyword",
                "top_k": 0,
            },
        )

    payload = _payload(
        await server.call_tool(
            "vera_search",
            {
                "file": str(approved_library["archive"]),
                "query": "restaurant",
                "mode": "keyword",
                "top_k": 50,
            },
        )
    )
    assert 1 <= len(payload["results"]) <= 1


@pytest.mark.anyio
async def test_bridge_corpus_search_denies_outside_and_drops_escaped_archives(
    approved_library, monkeypatch
):
    from vera_doc.corpus import VeraCorpus
    from vera_mcp import build_server

    policy = approved_library["policy"]
    real_open = VeraCorpus.open

    def open_with_escaped_member(directory, **kwargs):
        corpus = real_open(directory, **kwargs)
        corpus.paths = [*corpus.paths, str(approved_library["sentinel"])]
        return corpus

    monkeypatch.setattr(VeraCorpus, "open", open_with_escaped_member)
    server = build_server(policy=policy)
    with pytest.raises(Exception, match="(?i)denied"):
        await server.call_tool(
            "vera_corpus_search",
            {
                "directory": str(approved_library["sibling"]),
                "query": "UNIQUE_SENTINEL_PHRASE_XYZ",
                "mode": "keyword",
                "top_k": 5,
            },
        )

    payload = _payload(
        await server.call_tool(
            "vera_corpus_search",
            {
                "directory": str(approved_library["root"]),
                "query": "UNIQUE_SENTINEL_PHRASE_XYZ",
                "mode": "keyword",
                "top_k": 5,
            },
        )
    )
    results_blob = json.dumps(payload.get("results", []))
    skipped = payload.get("skipped_files", [])
    assert "UNIQUE_SENTINEL" not in results_blob
    assert str(approved_library["sentinel"]) not in json.dumps(payload)
    assert any(item.get("category") == "denied" for item in skipped)
    assert all(
        item.get("file") == "(omitted)" for item in skipped if item.get("category") == "denied"
    )


@pytest.mark.anyio
async def test_show_sources_honors_max_sources(approved_library):
    from vera_mcp import build_server

    policy = AccessPolicy(
        library_root=approved_library["policy"].library_root,
        max_sources=1,
    )
    server = build_server(policy=policy)
    chunk_id = _first_chunk(approved_library["archive"])
    with pytest.raises(Exception, match="(?i)at most 1 source"):
        await server.call_tool(
            "vera_show_sources",
            {
                "sources": [
                    {
                        "file": str(approved_library["archive"]),
                        "chunk_id": chunk_id,
                        "id": "C1",
                    },
                    {
                        "file": str(approved_library["archive"]),
                        "chunk_id": chunk_id,
                        "id": "C2",
                    },
                ]
            },
        )
