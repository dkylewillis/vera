import os
import sys

import pytest

from helpers.plugins import make_echo_wheel, write_notes_environment
from vera_app import convert as convert_handlers
from vera_app.sidecar import handle
from vera_doc import VeraDocument
from vera_ingest import reset_ingest_pipeline_registry
from vera_ingest.external import EXTERNAL_PYTHON_ENV


@pytest.fixture
def no_environment(monkeypatch):
    monkeypatch.delenv(EXTERNAL_PYTHON_ENV, raising=False)
    reset_ingest_pipeline_registry()
    yield
    reset_ingest_pipeline_registry()


@pytest.fixture
def notes_environment(tmp_path, monkeypatch):
    """A separate Python environment: this interpreter plus a ``notes`` pipeline."""
    folder = write_notes_environment(tmp_path / "environment")
    inherited = os.environ.get("PYTHONPATH", "")
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(filter(None, [str(folder), inherited])))
    monkeypatch.setenv(EXTERNAL_PYTHON_ENV, sys.executable)
    reset_ingest_pipeline_registry()
    yield folder
    reset_ingest_pipeline_registry()


def test_plugins_list_reports_no_environment_by_default(tmp_path, no_environment):
    listed = handle({"id": "l", "action": "plugins_list", "plugins_dir": str(tmp_path)})
    assert listed["ok"] is True, listed
    assert listed["result"]["environment"] == {"python": "", "pipelines": []}


def test_sidecar_converts_through_the_separate_environment(tmp_path, notes_environment):
    listed = handle({"id": "l", "action": "plugins_list", "plugins_dir": str(tmp_path)})
    assert listed["ok"] is True, listed
    assert listed["result"]["environment"]["python"] == sys.executable
    assert "notes" in listed["result"]["environment"]["pipelines"]
    assert not [
        error
        for error in listed["result"]["load_errors"]
        if error.startswith("Separate Python environment")
    ]

    described = handle({"id": "d", "action": "describe_ingest_pipelines"})
    assert "notes" in [item["spec"] for item in described["result"]["pipelines"]]

    source = tmp_path / "pond.note"
    source.write_text("Detention ponds are sized for the design storm.", encoding="utf-8")
    out = tmp_path / "pond.vera"
    converted = handle(
        {
            "id": "c",
            "action": "convert",
            "input": str(source),
            "output": str(out),
            "parser": "notes",
            "model": "hashing",
        }
    )
    assert converted["ok"] is True, converted
    with VeraDocument.open(str(out)) as document:
        assert document.inspect()["parser_name"] == "notes"


def test_docling_is_offered_only_when_the_environment_runs_it(monkeypatch):
    monkeypatch.setattr(convert_handlers, "is_external_pipeline", lambda provider: False)
    assert convert_handlers._excluded_from_desktop("docling:hybrid")
    assert not convert_handlers._excluded_from_desktop("pymupdf")
    with pytest.raises(ValueError, match="Settings > Plugins"):
        convert_handlers._reject_excluded_desktop_parser({"parser": "docling"})

    monkeypatch.setattr(convert_handlers, "is_external_pipeline", lambda provider: True)
    assert not convert_handlers._excluded_from_desktop("docling:hybrid")
    convert_handlers._reject_excluded_desktop_parser({"parser": "docling"})


def test_plugin_actions_install_list_and_remove_a_wheel(tmp_path):
    plugins = tmp_path / "plugins"
    wheel = make_echo_wheel(tmp_path)

    installed = handle(
        {"id": "i", "action": "plugin_install", "plugins_dir": str(plugins), "wheel": str(wheel)}
    )
    assert installed["ok"] is True, installed
    assert installed["result"]["pipelines"] == ["echo"]

    listed = handle({"id": "l", "action": "plugins_list", "plugins_dir": str(plugins)})
    assert listed["ok"] is True, listed
    assert [plugin["name"] for plugin in listed["result"]["plugins"]] == ["echo-ingest-plugin"]
    assert isinstance(listed["result"]["load_errors"], list)

    removed = handle(
        {
            "id": "r",
            "action": "plugin_remove",
            "plugins_dir": str(plugins),
            "name": "echo-ingest-plugin",
        }
    )
    assert removed["ok"] is True, removed
    assert (
        handle({"id": "l2", "action": "plugins_list", "plugins_dir": str(plugins)})["result"][
            "plugins"
        ]
        == []
    )


def test_plugin_actions_need_a_plugins_dir(tmp_path):
    response = handle({"id": "x", "action": "plugins_list"})
    assert response["ok"] is False
    assert "plugins_dir" in response["error"]
    bad = handle(
        {
            "id": "y",
            "action": "plugin_install",
            "plugins_dir": str(tmp_path),
            "wheel": str(tmp_path / "a.zip"),
        }
    )
    assert bad["ok"] is False
    assert ".whl" in bad["error"]
