"""Managed folder libraries: sync, trash, scope, and index source paths."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
from vera_doc.corpus import VeraCorpus
from vera_doc.library import (
    LIBRARY_DIRECTORY,
    LibraryBusyError,
    extended_path,
    read_state,
    sync_lock,
)
from vera_ingest.library import (
    LibraryUnreachableError,
    NestedLibraryError,
    init_library,
    library_status,
    list_trash,
    restore_from_trash,
    sync_library,
)

NOTE = "# Detention\n\nStormwater ponds must be sized for the design storm.\n"
OTHER = "# Sight distance\n\nRequired stopping sight distance is one hundred metres.\n"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


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
        _write(tmp_path / f"file-{index}.md", f"# File {index}\n\nUnique body {index} for search.\n")
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
