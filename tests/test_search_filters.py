"""Convert metadata stamps and search --where / --include filters."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from vera_cli.main import build_parser
from vera_doc import VeraCorpus, VeraDocument, build_library_index
from vera_doc.collection import CHUNK_METADATA_FILTER_REASON, discover_vera_files
from vera_doc.document import ChunkRecord
from vera_ingest import ReservedMetadataKeyError, convert


def _run_cli(*argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "vera_cli", *argv],
        text=True,
        capture_output=True,
        check=False,
    )


def _write_capacity_markdown(path: Path, company: str, sections: int = 8) -> None:
    blocks = [
        f"# {company} capacity {index}\n\n"
        f"{company} adding capacity discussion {index} unique_{company}_{index}.\n"
        for index in range(sections)
    ]
    path.write_text("\n".join(blocks), encoding="utf-8")


def _convert_company(path: Path, company: str, sections: int = 8) -> Path:
    source = path.with_suffix(".md")
    _write_capacity_markdown(source, company, sections=sections)
    convert(
        str(source),
        str(path),
        model="hashing",
        metadata={"company": company, "document_type": "filings"},
    )
    return path


def test_convert_stamps_archive_and_chunk_metadata(tmp_path: Path) -> None:
    source = tmp_path / "notes.md"
    source.write_text("# Detention\n\nPonds must detain the 25-year storm.\n", encoding="utf-8")
    out = tmp_path / "notes.vera"
    convert(str(source), str(out), metadata={"company": "GRID", "source_id": "src_aaa"})
    with VeraDocument.open(str(out)) as document:
        assert document.metadata["company"] == "GRID"
        assert document.metadata["source_id"] == "src_aaa"
        inspect = document.inspect()
        assert inspect["company"] == "GRID"
        chunks = document.get()
        assert chunks
        assert all(chunk.metadata["company"] == "GRID" for chunk in chunks)
        hits = document.search("detain", mode="keyword", where={"company": "GRID"})
        assert hits
        assert document.search("detain", mode="keyword", where={"company": "PWRX"}) == []


def test_convert_rejects_reserved_metadata_keys(tmp_path: Path) -> None:
    source = tmp_path / "notes.md"
    source.write_text("# Detention\n\nPonds must detain the 25-year storm.\n", encoding="utf-8")
    out = tmp_path / "notes.vera"
    with pytest.raises(ReservedMetadataKeyError, match="page_start"):
        convert(str(source), str(out), metadata={"page_start": 1})
    with pytest.raises(ReservedMetadataKeyError, match="source_file_hash"):
        convert(str(source), str(out), metadata={"source_file_hash": "abc"})


def test_cli_convert_metadata_and_where(tmp_path: Path) -> None:
    source = tmp_path / "notes.md"
    source.write_text("# Detention\n\nPonds must detain the 25-year storm.\n", encoding="utf-8")
    out = tmp_path / "notes.vera"
    converted = _run_cli(
        "convert",
        str(source),
        str(out),
        "--metadata",
        "company=GRID",
        "--json",
    )
    assert converted.returncode == 0, converted.stderr
    inspected = _run_cli("inspect", str(out), "--json")
    info = json.loads(inspected.stdout)
    assert info["company"] == "GRID"
    hit = _run_cli("search", str(out), "detain", "--where", "company=GRID", "--json")
    assert hit.returncode == 0, hit.stderr
    assert json.loads(hit.stdout)["results"]
    miss = _run_cli("search", str(out), "detain", "--where", "company=PWRX", "--json")
    assert miss.returncode == 0, miss.stderr
    assert json.loads(miss.stdout)["results"] == []


def test_cli_reserved_metadata_exits_2(tmp_path: Path) -> None:
    source = tmp_path / "notes.md"
    source.write_text("# Detention\n\nPonds.\n", encoding="utf-8")
    out = tmp_path / "notes.vera"
    proc = _run_cli(
        "convert",
        str(source),
        str(out),
        "--metadata",
        "page_start=1",
        "--json",
    )
    assert proc.returncode == 2
    payload = json.loads(proc.stdout)
    assert payload["ok"] is False
    assert "page_start" in payload["error"]


def test_cli_include_on_file_exits_2(tmp_path: Path) -> None:
    source = tmp_path / "notes.md"
    out = tmp_path / "notes.vera"
    source.write_text("# Detention\n\nPonds.\n", encoding="utf-8")
    convert(str(source), str(out))
    proc = _run_cli(
        "search",
        str(out),
        "Ponds",
        "--include",
        "notes.vera",
        "--json",
    )
    assert proc.returncode == 2
    payload = json.loads(proc.stdout)
    assert payload["ok"] is False
    assert "--include" in payload["error"]


def test_cli_where_without_equals_exits_2() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["search", "library", "query", "--where", "company"])
    assert exc.value.code == 2


def test_corpus_where_fills_top_k_from_matching_files(tmp_path: Path) -> None:
    library = tmp_path / "archives"
    library.mkdir()
    _convert_company(library / "grid.vera", "GRID", sections=8)
    _convert_company(library / "pwrx.vera", "PWRX", sections=8)
    with VeraCorpus.open(str(library), use_index=False) as corpus:
        mixed = corpus.search("adding capacity", mode="keyword", top_k=6)
        assert {Path(hit.file).name for hit in mixed} == {"grid.vera", "pwrx.vera"}
        grid = corpus.search(
            "adding capacity",
            mode="keyword",
            top_k=5,
            where={"company": "GRID"},
        )
        assert len(grid) == 5
        assert all(Path(hit.file).name == "grid.vera" for hit in grid)
        both = corpus.search(
            "adding capacity",
            mode="keyword",
            top_k=6,
            where={"company": ["GRID", "PWRX"]},
        )
        assert {Path(hit.file).name for hit in both} == {"grid.vera", "pwrx.vera"}
        and_filter = corpus.search(
            "adding capacity",
            mode="keyword",
            top_k=5,
            where={"company": "GRID", "document_type": "filings"},
        )
        assert and_filter
        assert all(Path(hit.file).name == "grid.vera" for hit in and_filter)
        miss = corpus.search(
            "adding capacity",
            mode="keyword",
            top_k=5,
            where={"company": "GRID", "document_type": "slides"},
        )
        assert miss == []


def test_include_exclude_discovery_matrix(tmp_path: Path) -> None:
    root = tmp_path / "proposals"
    (root / "utilities" / "2023").mkdir(parents=True)
    (root / "transportation" / "2024").mkdir(parents=True)
    (root / "archive").mkdir()
    _convert_company(root / "utilities" / "2023" / "water.vera", "WATER", sections=2)
    _convert_company(root / "transportation" / "2024" / "roadway.vera", "ROAD", sections=2)
    _convert_company(root / "archive" / "old.vera", "OLD", sections=2)

    all_recursive = discover_vera_files(root, recursive=True)
    assert len(all_recursive) == 3

    utilities = discover_vera_files(root, recursive=True, includes=["utilities/**"])
    assert [path.name for path in utilities] == ["water.vera"]

    included_then_excluded = discover_vera_files(
        root,
        recursive=True,
        includes=["archive"],
        excludes=["archive"],
    )
    assert included_then_excluded == []

    mixed = discover_vera_files(
        root,
        recursive=True,
        includes=["utilities/**", "archive"],
        excludes=["archive"],
    )
    assert [path.name for path in mixed] == ["water.vera"]

    no_includes = discover_vera_files(root, recursive=True, excludes=["archive"])
    assert {path.name for path in no_includes} == {"water.vera", "roadway.vera"}


def test_indexed_archive_where_and_chunk_fallback(tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()
    _convert_company(library / "grid.vera", "GRID", sections=6)
    _convert_company(library / "pwrx.vera", "PWRX", sections=6)
    build_library_index(str(library))

    with VeraCorpus.open(str(library)) as corpus:
        results = corpus.search(
            "adding capacity",
            mode="keyword",
            top_k=4,
            where={"company": "GRID"},
        )
        assert corpus.uses_index is True
        assert all(Path(hit.file).name == "grid.vera" for hit in results)
        assert len(results) == 4

    civil = library / "civil.vera"
    electrical = library / "electrical.vera"
    _chunk_only_archive(civil, "civil", "Civil adding capacity for the pond.")
    _chunk_only_archive(electrical, "electrical", "Electrical adding capacity for the feeder.")
    build_library_index(str(library))

    with VeraCorpus.open(str(library)) as corpus:
        results = corpus.search(
            "adding capacity",
            mode="keyword",
            top_k=4,
            where={"discipline": "civil"},
        )
        report = corpus.index_search_report()
        assert report["used"] is False
        assert CHUNK_METADATA_FILTER_REASON in report["reasons"]
        assert results
        assert all(hit.record.metadata.get("discipline") == "civil" for hit in results)


def _chunk_only_archive(path: Path, discipline: str, text: str) -> None:
    with VeraDocument.create(path) as document:
        document.add(
            [
                ChunkRecord(
                    id="chunk_0001",
                    text=text,
                    metadata={
                        "document_id": "document_0001",
                        "source_filename": path.name,
                        "page_start": 1,
                        "page_end": 1,
                        "heading_path": "Notes",
                        "discipline": discipline,
                    },
                )
            ]
        )


@pytest.mark.anyio
async def test_mcp_search_where_and_corpus_include(tmp_path: Path) -> None:
    from vera_mcp import build_server

    library = tmp_path / "library"
    nested = library / "companies" / "GRID" / "archives"
    nested.mkdir(parents=True)
    other = library / "companies" / "PWRX" / "archives"
    other.mkdir(parents=True)
    _convert_company(nested / "grid.vera", "GRID", sections=3)
    _convert_company(other / "pwrx.vera", "PWRX", sections=3)

    server = build_server()

    def payload(result):
        if isinstance(result, tuple):
            content, structured = result
            if structured is not None:
                return structured.get("result", structured)
            return json.loads(content[0].text)
        return result

    single = payload(
        await server.call_tool(
            "vera_search",
            {
                "file": str(nested / "grid.vera"),
                "query": "adding capacity",
                "mode": "keyword",
                "where": {"company": "GRID"},
                "top_k": 2,
            },
        )
    )
    assert single["results"]

    corpus = payload(
        await server.call_tool(
            "vera_corpus_search",
            {
                "directory": str(library),
                "query": "adding capacity",
                "mode": "keyword",
                "recursive": True,
                "includes": ["companies/GRID/archives/**"],
                "where": {"company": "GRID"},
                "top_k": 3,
            },
        )
    )
    assert corpus["results"]
    assert all(hit["file"].endswith("grid.vera") for hit in corpus["results"])


@pytest.fixture
def anyio_backend():
    return "asyncio"
