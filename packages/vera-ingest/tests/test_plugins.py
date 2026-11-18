"""Plugin folders: install pure-Python pipeline wheels and discover them by entry point."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pytest

from helpers.plugins import make_echo_wheel
from vera_doc import VeraDocument
from vera_ingest import convert, list_ingest_pipelines, reset_ingest_pipeline_registry
from vera_ingest.plugins import (
    PLUGIN_DIRS_ENV,
    activate_plugin_dirs,
    install_plugin_wheel,
    list_plugins,
    remove_plugin,
)


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.delenv(PLUGIN_DIRS_ENV, raising=False)
    reset_ingest_pipeline_registry()
    yield
    reset_ingest_pipeline_registry()


def test_installed_wheel_registers_its_pipeline_through_the_plugin_dirs_env(tmp_path, monkeypatch):
    plugins = tmp_path / "plugins"
    installed = install_plugin_wheel(make_echo_wheel(tmp_path), plugins)

    assert installed["name"] == "echo-ingest-plugin"
    assert installed["version"] == "0.0.1"
    assert installed["pipelines"] == ["echo"]
    assert installed["warnings"] == []
    assert (plugins / "echo-ingest-plugin" / "echo_ingest_plugin" / "__init__.py").is_file()
    assert "echo" not in list_ingest_pipelines()

    monkeypatch.setenv(PLUGIN_DIRS_ENV, str(plugins))
    reset_ingest_pipeline_registry()
    assert "echo" in list_ingest_pipelines()

    source = tmp_path / "note.pdf"
    source.write_text("Echoed plugin text about detention ponds.", encoding="utf-8")
    out = tmp_path / "note.vera"
    convert(str(source), str(out), model="hashing", parser="echo", store_original=False)
    with VeraDocument.open(str(out)) as document:
        assert document.inspect()["parser_name"] == "echo"


def test_reinstall_replaces_the_older_copy_and_remove_deletes_it(tmp_path):
    plugins = tmp_path / "plugins"
    install_plugin_wheel(make_echo_wheel(tmp_path, version="0.0.1"), plugins)
    upgraded = install_plugin_wheel(make_echo_wheel(tmp_path, version="0.0.2"), plugins)

    assert upgraded["version"] == "0.0.2"
    assert [plugin["version"] for plugin in list_plugins(plugins)] == ["0.0.2"]
    assert [child.name for child in plugins.iterdir()] == ["echo-ingest-plugin"]

    assert remove_plugin("echo_ingest_plugin", plugins) == {
        "name": "echo-ingest-plugin",
        "removed": True,
    }
    assert list_plugins(plugins) == []
    with pytest.raises(ValueError, match="No plugin named"):
        remove_plugin("echo-ingest-plugin", plugins)
    with pytest.raises(ValueError, match="No plugin named"):
        remove_plugin("..", plugins)


def test_install_rejects_compiled_wheels_and_non_pipeline_packages(tmp_path):
    plugins = tmp_path / "plugins"
    with pytest.raises(ValueError, match="Only pure-Python plugins"):
        install_plugin_wheel(make_echo_wheel(tmp_path, tag="cp312-cp312-win_amd64"), plugins)
    with pytest.raises(ValueError, match="does not register a VERA ingest pipeline"):
        install_plugin_wheel(
            make_echo_wheel(tmp_path, entry_points="[console_scripts]\necho = x:y\n"), plugins
        )
    not_a_wheel = tmp_path / "plugin.whl"
    not_a_wheel.write_text("nope", encoding="utf-8")
    with pytest.raises(ValueError, match="not a valid wheel"):
        install_plugin_wheel(not_a_wheel, plugins)
    with pytest.raises(ValueError, match=r"\.whl"):
        install_plugin_wheel(tmp_path / "plugin.zip", plugins)
    assert not plugins.exists() or list_plugins(plugins) == []


def test_install_rejects_entries_that_escape_the_plugin_folder(tmp_path):
    wheel = make_echo_wheel(tmp_path)
    with zipfile.ZipFile(wheel, "a") as archive:
        archive.writestr("../escaped.py", "x = 1\n")
    plugins = tmp_path / "plugins"
    with pytest.raises(ValueError, match="outside the plugin folder"):
        install_plugin_wheel(wheel, plugins)
    assert not (tmp_path / "escaped.py").exists()
    assert list_plugins(plugins) == []


def test_install_warns_about_missing_requirements_and_taken_names(tmp_path):
    wheel = make_echo_wheel(
        tmp_path,
        requires=("vera-ingest", "definitely-not-installed-vera-dep>=1", 'pytest; extra == "dev"'),
        entry_points="[vera.ingest_pipelines]\npymupdf = echo_ingest_plugin:create_pipeline\n",
    )
    installed = install_plugin_wheel(wheel, tmp_path / "plugins")
    assert len(installed["warnings"]) == 2
    assert "definitely-not-installed-vera-dep" in installed["warnings"][0]
    assert "'pymupdf' is already installed" in installed["warnings"][1]


def test_activation_appends_plugin_folders_after_existing_paths(tmp_path):
    plugins = tmp_path / "plugins"
    install_plugin_wheel(make_echo_wheel(tmp_path), plugins)
    (plugins / ".install-leftover").mkdir()
    first = sys.path[0]

    added = activate_plugin_dirs([plugins])

    assert added == [str(plugins / "echo-ingest-plugin")]
    assert sys.path[0] == first
    assert sys.path[-1] == str(plugins / "echo-ingest-plugin")
    assert activate_plugin_dirs([plugins]) == []
    assert activate_plugin_dirs([Path(tmp_path / "missing")]) == []
