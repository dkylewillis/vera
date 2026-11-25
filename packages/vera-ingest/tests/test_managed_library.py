"""Managed folder libraries: sync, trash, scope, and index source paths."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from vera_doc import library_index_status
from vera_doc.corpus import VeraCorpus
from vera_doc.library import (
    LIBRARY_DIRECTORY,
    LibraryBusyError,
    extended_path,
    read_state,
    sync_lock,
)
from vera_ingest.library import (
    NestedLibraryError,
    init_library,
    library_pipelines,
    library_status,
    list_trash,
    restore_from_trash,
    set_folder_pipeline,
    sync_library,
)


@pytest.fixture(autouse=True)
def _alt_pdf_pipeline():
    """Folder-rule tests need a second PDF pipeline besides ``pymupdf``."""
    from vera_ingest.descriptors import PipelineCapabilities, PipelineDescriptor
    from vera_ingest.pipeline import (
        register_ingest_pipeline,
        register_ingest_pipeline_descriptor,
        reset_ingest_pipeline_registry,
    )
    from vera_ingest.types import ensure_ingest_request
    from vera_ingest_pymupdf import PyMuPDFOptions, run_pymupdf_pipeline

    def pipeline(source_path: str, options: object):
        request = ensure_ingest_request(options)
        config = PyMuPDFOptions.from_mapping(request.pipeline_options)
        return run_pymupdf_pipeline(source_path, request, config, parser_name="altpdf")

    def descriptor(variant: str = "default") -> PipelineDescriptor:
        del variant
        return PipelineDescriptor(
            provider="altpdf",
            variant="",
            spec="altpdf",
            label="altpdf",
            capabilities=PipelineCapabilities(source_formats=("pdf",)),
        )

    register_ingest_pipeline("altpdf", lambda variant="default": pipeline, replace=True)
    register_ingest_pipeline_descriptor("altpdf", descriptor, replace=True)
    try:
        yield
    finally:
        reset_ingest_pipeline_registry()


NOTE = "# Detention\n\nStormwater ponds must be sized for the design storm.\n"
OTHER = "# Sight distance\n\nRequired stopping sight distance is one hundred metres.\n"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_adopt_accepts_extension_keeping_and_legacy_siblings(tmp_path: Path):
    from vera_ingest import convert

    plans = tmp_path / "Plans"
    current = plans / "Current.md"
    legacy = plans / "Legacy.md"
    _write(current, NOTE)
    _write(legacy, OTHER)
    convert(str(current), str(plans / "Current.md.vera"), model="hashing")
    convert(str(legacy), str(plans / "Legacy.vera"), model="hashing")

    status = library_status(str(tmp_path))
    assert set(status["adoptable"]) == {"Plans/Current.md", "Plans/Legacy.md"}

    created = init_library(str(tmp_path), adopt=True, model="hashing")
    assert created["ok"]
    archives = tmp_path / ".vera" / "archives" / "Plans"
    assert (archives / "Current.md.vera").is_file()
    assert (archives / "Legacy.md.vera").is_file()
    assert not (plans / "Current.md.vera").exists()
    assert not (plans / "Legacy.vera").exists()


def test_init_adopt_sync_and_source_path_search(tmp_path: Path):
    plans = tmp_path / "Plans"
    _write(plans / "Site Plan.md", NOTE)
    sibling = plans / "Site Plan.vera"
    from vera_ingest import convert

    convert(str(plans / "Site Plan.md"), str(sibling), model="hashing")
    created = init_library(str(tmp_path), adopt=True, model="hashing")
    assert created["ok"]
    assert not sibling.exists()
    archive = tmp_path / ".vera" / "archives" / "Plans" / "Site Plan.md.vera"
    assert archive.is_file()
    assert (tmp_path / ".vera" / "README.txt").is_file()
    assert (tmp_path / ".vera" / "library.json").is_file()

    _write(tmp_path / "Reports" / "Study.md", OTHER)
    report = sync_library(str(tmp_path))
    assert report["ok"]
    assert report["converted"] == 1
    assert report["moved"] == 0
    assert (tmp_path / ".vera" / "index").is_dir()

    corpus = VeraCorpus.open(str(tmp_path))
    try:
        hits = corpus.search(text="stopping sight distance", mode="keyword", top_k=5)
    finally:
        corpus.close()
    assert hits
    assert hits[0].source_path == "Reports/Study.md"
    assert hits[0].as_dict()["source_path"] == "Reports/Study.md"

    scoped = VeraCorpus.open(str(plans))
    try:
        scoped_hits = scoped.search(text="stopping sight distance", mode="keyword", top_k=5)
        local_hits = scoped.search(text="design storm", mode="keyword", top_k=5)
    finally:
        scoped.close()
    assert scoped_hits == []
    assert local_hits
    assert local_hits[0].source_path == "Plans/Site Plan.md"

    included = VeraCorpus.open(str(tmp_path), includes=["Reports/**"])
    try:
        included_hits = included.search(text="design storm", mode="keyword", top_k=5)
    finally:
        included.close()
    assert included_hits == []


def test_sync_skips_office_owner_files(tmp_path: Path):
    _write(tmp_path / "notes.md", NOTE)
    (tmp_path / "~$notes.md").write_text("lock", encoding="utf-8")
    (tmp_path / "~$DKSalaries.xlsx").write_bytes(b"lock")
    init_library(str(tmp_path), model="hashing")
    report = sync_library(str(tmp_path))
    assert report["converted"] == 1
    assert report["errors"] == []
    archives = tmp_path / ".vera" / "archives"
    converted = [action for action in report["actions"] if action["action"] == "convert"]
    assert len(converted) == 1
    assert Path(converted[0]["output"]) == archives / "notes.md.vera"
    assert converted[0]["warnings"] == []
    assert (archives / "notes.md.vera").is_file()
    assert not (archives / "~$notes.md.vera").exists()
    assert not (archives / "~$DKSalaries.xlsx.vera").exists()


def test_sync_leaves_a_fresh_index_unchanged(tmp_path: Path):
    init_library(str(tmp_path), model="hashing")
    _write(tmp_path / "notes.md", NOTE)
    first_events: list[dict] = []
    assert sync_library(str(tmp_path), progress=first_events.append)["converted"] == 1
    built = library_index_status(str(tmp_path), verify_hashes=False)
    assert built["fresh"] is True
    generation = built["generation_id"]
    assert generation

    quiet: list[dict] = []
    again = sync_library(str(tmp_path), progress=quiet.append)
    assert again["converted"] == 0
    assert again["index"]["fresh"] is True
    assert again["index"]["generation_id"] == generation
    assert [event["phase"] for event in quiet if event["phase"] in {"discovering", "indexing", "finalizing"}] == []

    _write(tmp_path / "notes.md", OTHER)
    changed: list[dict] = []
    assert sync_library(str(tmp_path), progress=changed.append)["converted"] == 1
    updated = library_index_status(str(tmp_path), verify_hashes=False)
    assert updated["fresh"] is True
    assert updated["generation_id"] != generation
    assert "indexing" in {event["phase"] for event in changed}


def test_convert_progress_counts_only_documents_this_run_will_convert(tmp_path: Path):
    init_library(str(tmp_path), model="hashing")
    _write(tmp_path / "a.md", NOTE)
    _write(tmp_path / "b.md", OTHER)
    events: list[dict] = []
    first = sync_library(str(tmp_path), progress=events.append)
    assert first["converted"] == 2
    converts = [event for event in events if event["phase"] == "convert"]
    assert [(event["completed"], event["total"], event["input"]) for event in converts] == [
        (0, 2, "a.md"),
        (1, 2, "b.md"),
    ]

    events.clear()
    (tmp_path / "a.md").rename(tmp_path / "a-renamed.md")
    (tmp_path / "b.md").unlink()
    _write(tmp_path / "c.md", NOTE)
    second = sync_library(str(tmp_path), progress=events.append)
    assert second["moved"] == 1
    assert second["converted"] == 1
    assert second["trashed"] == 1
    moves = [event for event in events if event["phase"] == "move"]
    converts = [event for event in events if event["phase"] == "convert"]
    trashes = [event for event in events if event["phase"] == "trash"]
    assert [(event["completed"], event["total"], event["input"]) for event in moves] == [
        (0, 1, "a-renamed.md"),
    ]
    assert [(event["completed"], event["total"], event["input"]) for event in converts] == [
        (0, 1, "c.md"),
    ]
    assert [(event["completed"], event["total"], event["input"]) for event in trashes] == [
        (0, 1, "b.md"),
    ]


def test_rename_move_delete_restore_and_purge(tmp_path: Path):
    source = tmp_path / "notes.md"
    _write(source, NOTE)
    init_library(str(tmp_path), model="hashing")
    assert sync_library(str(tmp_path))["converted"] == 1

    renamed = tmp_path / "renamed.md"
    source.rename(renamed)
    moved = sync_library(str(tmp_path))
    assert moved["moved"] == 1
    assert moved["converted"] == 0
    assert (tmp_path / ".vera" / "archives" / "renamed.md.vera").is_file()
    assert not (tmp_path / ".vera" / "archives" / "notes.md.vera").exists()

    nested = tmp_path / "Reports" / "renamed.md"
    nested.parent.mkdir()
    renamed.rename(nested)
    relocated = sync_library(str(tmp_path))
    assert relocated["moved"] == 1
    assert relocated["converted"] == 0

    nested.unlink()
    deleted = sync_library(str(tmp_path))
    assert deleted["trashed"] == 1
    assert deleted["needs_confirmation"] is False
    trash = list_trash(str(tmp_path))["entries"]
    assert len(trash) == 1
    restored = restore_from_trash(str(tmp_path), trash[0]["entry"])
    assert Path(restored["restored"]).is_file()
    assert Path(restored["restored"]).read_text(encoding="utf-8") == NOTE

    old = tmp_path / ".vera" / "trash" / "20200101T000000000000Z"
    old.mkdir(parents=True)
    (old / "gone.md.vera").write_bytes(b"placeholder")
    purged = sync_library(str(tmp_path))
    assert purged["purged"] >= 1
    assert not old.exists()


def test_mass_delete_guard_and_unreachable_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    init_library(str(tmp_path), model="hashing")
    for index in range(6):
        _write(
            tmp_path / f"file-{index}.md", f"# File {index}\n\nUnique body {index} for search.\n"
        )
    assert sync_library(str(tmp_path))["converted"] == 6
    for index in range(6):
        (tmp_path / f"file-{index}.md").unlink()
    held = sync_library(str(tmp_path))
    assert held["needs_confirmation"] is True
    assert held["trashed"] == 0
    assert held["pending_trash"] == 6
    assert len(list((tmp_path / ".vera" / "archives").rglob("*.vera"))) == 6
    confirmed = sync_library(str(tmp_path), confirm_deletes=True)
    assert confirmed["trashed"] == 6
    assert list((tmp_path / ".vera" / "archives").rglob("*.vera")) == []

    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("network disconnected")

    monkeypatch.setattr("vera_ingest.library.os.walk", boom)
    unreachable = sync_library(str(tmp_path))
    assert unreachable["needs_confirmation"] is True
    assert unreachable["trashed"] == 0
    assert "unreachable" in unreachable["error"]


def test_refuses_nested_library_and_lock(tmp_path: Path):
    init_library(str(tmp_path), model="hashing")
    child = tmp_path / "Plans"
    child.mkdir()
    with pytest.raises(NestedLibraryError):
        init_library(str(child), model="hashing")
    with sync_lock(tmp_path):
        with pytest.raises(LibraryBusyError):
            with sync_lock(tmp_path):
                pass


def test_first_sync_skips_hashing_and_scanning_reports_only_files_that_need_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    init_library(str(tmp_path), model="hashing")
    _write(tmp_path / "a.md", NOTE)
    _write(tmp_path / "b.md", OTHER)
    hashed: list[str] = []
    real_hash = __import__("vera_ingest.library", fromlist=["_hash_file"])._hash_file

    def counting_hash(path: Path, cancel: object = None) -> str:
        hashed.append(str(path))
        return real_hash(path, cancel)

    monkeypatch.setattr("vera_ingest.library._hash_file", counting_hash)
    events: list[dict] = []
    first = sync_library(str(tmp_path), progress=events.append)
    assert first["converted"] == 2
    assert hashed == []
    assert [event for event in events if event["phase"] == "scanning"] == []
    state = read_state(tmp_path)
    assert state["a.md"]["hash"] == hashlib.sha256((tmp_path / "a.md").read_bytes()).hexdigest()
    assert state["b.md"]["hash"] == hashlib.sha256((tmp_path / "b.md").read_bytes()).hexdigest()

    hashed.clear()
    events.clear()
    _write(tmp_path / "b.md", OTHER + "\nEdited.\n")
    _write(tmp_path / "c.md", NOTE)
    second = sync_library(str(tmp_path), progress=events.append)
    assert second["converted"] == 2
    scanning = [event for event in events if event["phase"] == "scanning"]
    assert len(scanning) == 1
    assert scanning[0]["input"] == "b.md"
    assert scanning[0]["completed"] == 0
    assert scanning[0]["total"] == 1
    assert len(hashed) == 1
    assert hashed[0].endswith("b.md")


def test_hash_stops_on_the_next_block(tmp_path: Path):
    path = tmp_path / "large.bin"
    path.write_bytes(b"x" * (2 * 1024 * 1024))

    class StopAfterFirstBlock:
        def __init__(self) -> None:
            self.checks = 0

        def raise_if_cancelled(self) -> None:
            self.checks += 1
            if self.checks > 1:
                raise RuntimeError("stopped")

    from vera_ingest.library import _hash_file

    with pytest.raises(RuntimeError, match="stopped"):
        _hash_file(path, StopAfterFirstBlock())


def test_status_reports_pending_work_without_converting(tmp_path: Path):
    _write(tmp_path / "notes.md", NOTE)
    init_library(str(tmp_path), model="hashing")
    status = library_status(str(tmp_path))
    assert status["managed"] is True
    assert status["converted"] == 1
    assert not (tmp_path / ".vera" / "archives" / "notes.md.vera").exists()


def test_deep_windows_path_converts(tmp_path: Path):
    init_library(str(tmp_path), model="hashing")
    deep = tmp_path
    for index in range(30):
        deep = deep / f"folder{index:02d}"
    os.makedirs(extended_path(deep), exist_ok=True)
    source = deep / "notes.md"
    with open(extended_path(source), "w", encoding="utf-8") as handle:
        handle.write(NOTE)
    report = sync_library(str(tmp_path))
    assert report["failed"] == 0, report["errors"]
    assert report["converted"] == 1


def test_plain_recursive_search_skips_trash(tmp_path: Path):
    _write(tmp_path / "notes.md", NOTE)
    init_library(str(tmp_path), model="hashing")
    sync_library(str(tmp_path))
    (tmp_path / "notes.md").unlink()
    sync_library(str(tmp_path))
    from vera_doc.collection import discover_vera_files

    found = [path.name for path in discover_vera_files(tmp_path, recursive=True)]
    assert found == []
    assert list_trash(str(tmp_path))["entries"]


def _parser_name(root: Path, source_rel: str) -> str:
    from vera_doc import VeraDocument

    archive = root / LIBRARY_DIRECTORY / "archives" / f"{source_rel}.vera"
    with VeraDocument.open(str(archive)) as document:
        return document.inspect()["parser_name"]


def _mixed_library(root: Path) -> None:
    from helpers.pdfs import make_topic_pdf

    (root / "Plans").mkdir(parents=True)
    (root / "Docs").mkdir(parents=True)
    make_topic_pdf(root / "Plans" / "C701.pdf", "CONSTRUCTION DETAILS", "Doghouse manhole detail.")
    make_topic_pdf(root / "Docs" / "Manual.pdf", "Stormwater Manual", "Detention is required.")
    _write(root / "Plans" / "Notes.md", NOTE)


def test_folder_rule_picks_the_pipeline_for_its_pdfs_only(tmp_path: Path):
    _mixed_library(tmp_path)
    init_library(str(tmp_path), model="hashing")
    rules = set_folder_pipeline(str(tmp_path / "Plans"), parser="altpdf")
    assert rules["folder"] == "Plans"
    assert rules["rules"] == [{"folder": "Plans", "parser": "altpdf", "pipeline_options": {}}]

    pending = library_status(str(tmp_path))
    assert pending["pipeline_rules"] == rules["rules"]
    parsers = {action["source"]: action.get("parser") for action in pending["actions"]}
    assert parsers == {
        "Plans/C701.pdf": "altpdf",
        "Plans/Notes.md": None,
        "Docs/Manual.pdf": None,
    }

    report = sync_library(str(tmp_path))
    assert report["ok"], report["errors"]
    assert report["converted"] == 3
    assert _parser_name(tmp_path, "Plans/C701.pdf") == "altpdf"
    assert _parser_name(tmp_path, "Plans/Notes.md") == "markdown"
    assert _parser_name(tmp_path, "Docs/Manual.pdf") == "pymupdf"
    assert read_state(tmp_path)["Plans/C701.pdf"]["pipeline"] == "altpdf"
    assert read_state(tmp_path)["Docs/Manual.pdf"]["pipeline"] == ""
    assert sync_library(str(tmp_path))["converted"] == 0


def test_changing_a_rule_reconverts_only_the_files_it_affects(tmp_path: Path):
    _mixed_library(tmp_path)
    init_library(str(tmp_path), model="hashing")
    set_folder_pipeline(str(tmp_path), folder="Plans", parser="altpdf")
    sync_library(str(tmp_path))

    cleared = set_folder_pipeline(str(tmp_path), folder="Plans", clear=True)
    assert cleared["rules"] == []
    pending = library_status(str(tmp_path))
    converts = [action for action in pending["actions"] if action["action"] == "convert"]
    assert converts == [
        {
            "action": "convert",
            "source": "Plans/C701.pdf",
            "size": converts[0]["size"],
            "mtime_ns": converts[0]["mtime_ns"],
            "hash": converts[0]["hash"],
            "reason": "pipeline",
            "parser": None,
        }
    ]
    report = sync_library(str(tmp_path))
    assert report["converted"] == 1
    assert _parser_name(tmp_path, "Plans/C701.pdf") == "pymupdf"


def test_moving_a_pdf_into_a_plans_folder_reconverts_it(tmp_path: Path):
    _mixed_library(tmp_path)
    init_library(str(tmp_path), model="hashing")
    set_folder_pipeline(str(tmp_path / "Plans"), parser="altpdf")
    sync_library(str(tmp_path))

    (tmp_path / "Docs" / "Manual.pdf").rename(tmp_path / "Plans" / "Manual.pdf")
    report = sync_library(str(tmp_path))
    assert report["ok"], report["errors"]
    assert report["moved"] == 0
    assert report["converted"] == 1
    assert report["trashed"] == 1
    assert _parser_name(tmp_path, "Plans/Manual.pdf") == "altpdf"


def test_rule_added_before_state_recorded_pipelines_checks_the_archive(tmp_path: Path):
    from vera_doc.library import write_state

    _mixed_library(tmp_path)
    init_library(str(tmp_path), model="hashing")
    sync_library(str(tmp_path))
    legacy_state = {
        source: {key: value for key, value in entry.items() if key != "pipeline"}
        for source, entry in read_state(tmp_path).items()
    }
    write_state(tmp_path, legacy_state)

    set_folder_pipeline(str(tmp_path), parser="altpdf")
    report = sync_library(str(tmp_path))
    assert report["converted"] == 2
    assert _parser_name(tmp_path, "Docs/Manual.pdf") == "altpdf"
    assert _parser_name(tmp_path, "Plans/Notes.md") == "markdown"


def test_deepest_matching_rule_wins_and_wildcards_match_one_folder():
    from vera_ingest.library import _PipelineResolver

    resolver = _PipelineResolver(
        {
            "convert": {
                "pipeline_options": {"chunk_size": 400},
                "pipeline_rules": [
                    {"folder": "", "parser": "altpdf"},
                    {
                        "folder": "Projects/*/Reports",
                        "parser": "pymupdf",
                        "pipeline_options": {"ocr_mode": "off"},
                    },
                ],
            }
        }
    )
    assert resolver.resolve("Sheet.pdf") == ("altpdf", {"chunk_size": 400})
    assert resolver.resolve("Projects/Lagrange/Reports/Study.pdf") == (
        "pymupdf",
        {"chunk_size": 400, "ocr_mode": "off"},
    )
    assert resolver.resolve("projects/lagrange/reports/deep/Study.pdf")[0] == "pymupdf"
    assert resolver.resolve("Projects/A/B/Reports/Study.pdf")[0] == "altpdf"
    assert resolver.resolve("Projects/Lagrange/Reports/Notes.md") == (None, {"chunk_size": 400})


def test_folder_rules_are_validated(tmp_path: Path):
    init_library(str(tmp_path), model="hashing")
    with pytest.raises(ValueError, match="Unknown ingest pipeline"):
        set_folder_pipeline(str(tmp_path), folder="Plans", parser="blueprints")
    with pytest.raises(ValueError, match="needs a parser"):
        set_folder_pipeline(str(tmp_path), folder="Plans")
    with pytest.raises(ValueError, match="inside the library"):
        set_folder_pipeline(str(tmp_path), folder="../Elsewhere", parser="altpdf")
    with pytest.raises(ValueError, match="managed by VERA"):
        set_folder_pipeline(str(tmp_path), folder=".vera/archives", parser="altpdf")
    assert library_pipelines(str(tmp_path))["rules"] == []


def test_a_folder_keeps_one_rule_per_file_type(tmp_path: Path):
    init_library(str(tmp_path), model="hashing")
    set_folder_pipeline(str(tmp_path), folder="Plans", parser="markdown")
    set_folder_pipeline(str(tmp_path), folder="Plans", parser="altpdf")

    def rules():
        return [
            (rule["folder"], rule["parser"]) for rule in library_pipelines(str(tmp_path))["rules"]
        ]

    assert rules() == [("Plans", "markdown"), ("Plans", "altpdf")]

    set_folder_pipeline(str(tmp_path), folder="Plans", parser="pymupdf")
    assert rules() == [("Plans", "markdown"), ("Plans", "pymupdf")]

    set_folder_pipeline(str(tmp_path), folder="Plans", clear=True, source_format="pdf")
    assert rules() == [("Plans", "markdown")]

    set_folder_pipeline(str(tmp_path), folder="Plans", clear=True)
    assert rules() == []
