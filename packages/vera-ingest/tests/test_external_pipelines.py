"""Pipelines in a separate Python environment (``VERA_PIPELINE_PYTHON``).

The "environment" here is this interpreter plus a folder on the child's
``PYTHONPATH`` that holds a ``notes`` pipeline. This process never imports
that folder, so ``notes`` exists only on the other side of the handoff.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

from helpers.plugins import write_notes_environment
from vera_doc import VeraDocument, get_embedder
from vera_doc.library import read_state
from vera_ingest import (
    ExternalPipelineError,
    PipelineDescriptor,
    batch_convert,
    convert,
    describe_ingest_pipeline,
    external_pipeline_status,
    get_ingest_pipeline,
    installed_source_formats,
    is_external_pipeline,
    list_ingest_pipeline_load_errors,
    list_ingest_pipelines,
    pick_parser_for_suffix,
    prefer_external_pipelines,
    register_ingest_pipeline,
    reset_ingest_pipeline_registry,
)
from vera_ingest import pipeline as pipeline_registry
from vera_ingest.external import EXTERNAL_PYTHON_ENV, resolve_python
from vera_ingest.library import init_library, set_folder_pipeline, sync_library


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.delenv(EXTERNAL_PYTHON_ENV, raising=False)
    monkeypatch.setattr(pipeline_registry, "_EXTERNAL_PREFERRED", set())
    reset_ingest_pipeline_registry()
    yield
    reset_ingest_pipeline_registry()


@pytest.fixture
def environment(tmp_path, monkeypatch):
    """Point ``VERA_PIPELINE_PYTHON`` at an interpreter that has the ``notes`` pipeline."""
    folder = write_notes_environment(tmp_path / "environment")
    inherited = os.environ.get("PYTHONPATH", "")
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(filter(None, [str(folder), inherited])))
    monkeypatch.setenv(EXTERNAL_PYTHON_ENV, sys.executable)
    reset_ingest_pipeline_registry()
    return folder


def _note(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_environment_pipelines_are_listed_and_only_run_when_named(environment):
    assert "notes" in list_ingest_pipelines()
    assert is_external_pipeline("notes")
    assert external_pipeline_status() == {"python": sys.executable, "pipelines": ["notes"]}
    assert describe_ingest_pipeline("notes").label == "notes (separate environment test)"

    # Pipelines this process already has stay local.
    assert not is_external_pipeline("pymupdf")
    assert not is_external_pipeline("no-such-pipeline")

    # A file extension never selects a pipeline from the other environment.
    assert pick_parser_for_suffix("pdf") == "pymupdf"
    assert "note" not in installed_source_formats()
    with pytest.raises(ValueError, match=r"No installed ingest pipeline supports \.note"):
        pick_parser_for_suffix("note")

    with pytest.raises(RuntimeError, match="separate Python environment"):
        get_ingest_pipeline("notes")("a.note", None)


def test_convert_and_batch_convert_run_in_the_environment(environment, tmp_path):
    source = _note(
        tmp_path / "docs" / "pond.note", "Detention ponds are sized for the design storm."
    )
    out = tmp_path / "pond.vera"

    written = convert(
        str(source),
        str(out),
        model="hashing",
        parser="notes",
        pipeline_options={"mark": "kept"},
        metadata={"company": "GRID"},
    )

    assert written == str(out)
    with VeraDocument.open(str(out)) as document:
        assert document.inspect()["parser_name"] == "notes"
        assert document.metadata["chunking_strategy"] == "whole:kept"
        assert document.metadata["company"] == "GRID"

    _note(tmp_path / "docs" / "broken.note", "FAIL on purpose")
    report = batch_convert(str(tmp_path / "docs"), parser="notes", model="hashing")
    assert report["converted"] == 1
    assert report["outputs"] == [str(source) + ".vera"]
    assert [error["error"] for error in report["errors"]] == [
        "the notes pipeline refused this file"
    ]
    assert not (tmp_path / "docs" / "broken.note.vera").exists()

    with pytest.raises(ValueError, match="embedding_function"):
        convert(
            str(source),
            str(tmp_path / "again.vera"),
            parser="notes",
            embedding_function=get_embedder("hashing"),
        )


def test_cancel_stops_the_conversion_in_the_environment(environment, tmp_path):
    source = _note(tmp_path / "slow.note", "SLOW pipeline that never finishes in time")
    heartbeat = Path(str(source) + ".heartbeat")
    out = tmp_path / "slow.vera"

    class Stopped(Exception):
        pass

    class StopOnceRunning:
        deadline = time.monotonic() + 90

        def raise_if_cancelled(self) -> None:
            if heartbeat.exists() or time.monotonic() > self.deadline:
                raise Stopped

    with pytest.raises(Stopped):
        convert(str(source), str(out), model="hashing", parser="notes", cancel=StopOnceRunning())

    assert heartbeat.exists(), "the pipeline never started in the other environment"
    assert not out.exists()
    last_beat = heartbeat.read_text(encoding="utf-8")
    time.sleep(0.6)
    assert heartbeat.read_text(encoding="utf-8") == last_beat, "the child kept running"


def test_a_host_can_prefer_the_environment_over_its_own_copy(environment):
    def local_factory(variant=""):
        return lambda source_path, request: None

    register_ingest_pipeline("notes", local_factory)
    assert not is_external_pipeline("notes")

    prefer_external_pipelines(["notes"])
    assert is_external_pipeline("notes")

    # The preference is host configuration and survives a registry reset.
    reset_ingest_pipeline_registry()
    register_ingest_pipeline("notes", local_factory)
    assert is_external_pipeline("notes")


def test_library_rule_can_use_an_environment_pipeline(environment, tmp_path):
    library = tmp_path / "library"
    _note(library / "Notes" / "a.note", "Sight distance is one hundred metres.")
    _note(library / "Other" / "b.note", "No rule covers this folder.")
    _note(library / "Other" / "c.md", "# Detention\n\nPonds are sized for the design storm.\n")
    init_library(str(library), model="hashing")
    set_folder_pipeline(str(library), folder="Notes", parser="notes")

    report = sync_library(str(library))

    assert report["ok"], report["errors"]
    assert report["converted"] == 2
    state = read_state(library)
    assert state["Notes/a.note"]["pipeline"] == "notes"
    assert "Other/c.md" in state
    # Only the rule's pipeline reads .note, so the same type elsewhere is not a document.
    assert "Other/b.note" not in state
    assert sync_library(str(library))["converted"] == 0


def test_a_broken_environment_is_reported_and_local_pipelines_still_work(tmp_path, monkeypatch):
    missing = tmp_path / "gone" / "python.exe"
    monkeypatch.setenv(EXTERNAL_PYTHON_ENV, str(missing))
    reset_ingest_pipeline_registry()

    assert "pymupdf" in list_ingest_pipelines()
    assert external_pipeline_status() == {"python": str(missing), "pipelines": []}
    errors = list_ingest_pipeline_load_errors()
    assert len(errors) == 1
    assert errors[0].startswith(f"Separate Python environment {missing}:")
    assert "does not exist" in errors[0]


def test_resolve_python_accepts_an_interpreter_or_an_environment_folder(tmp_path):
    assert resolve_python(sys.executable) == Path(sys.executable)

    windows = tmp_path / "win-env"
    (windows / "Scripts").mkdir(parents=True)
    (windows / "Scripts" / "python.exe").write_bytes(b"")
    assert resolve_python(windows) == windows / "Scripts" / "python.exe"

    posix = tmp_path / "posix-env"
    (posix / "bin").mkdir(parents=True)
    (posix / "bin" / "python").write_bytes(b"")
    assert resolve_python(posix) == posix / "bin" / "python"

    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ExternalPipelineError, match="No Python interpreter found"):
        resolve_python(empty)


def test_descriptor_survives_a_json_round_trip():
    described = describe_ingest_pipeline("pymupdf")
    wire = json.loads(json.dumps({**described.as_dict(), "added_by_a_newer_version": True}))

    assert PipelineDescriptor.from_dict(wire) == described
    with pytest.raises(ValueError, match="no provider"):
        PipelineDescriptor.from_dict({"label": "nameless"})
