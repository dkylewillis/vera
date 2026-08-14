from __future__ import annotations

from pathlib import Path

import pytest

from test_convert_search import make_pdf
from vera_ingest.convert import convert
from vera_ingest.pipeline import (
    PLUGIN_API_VERSION,
    PipelineDescriptor,
    UnknownIngestPipelineError,
    describe_ingest_pipeline,
    get_ingest_pipeline,
    list_ingest_pipeline_descriptors,
    list_ingest_pipelines,
    register_ingest_pipeline,
    register_ingest_pipeline_descriptor,
    reset_ingest_pipeline_registry,
)


@pytest.fixture(autouse=True)
def _reset_registry():
    reset_ingest_pipeline_registry()
    yield
    reset_ingest_pipeline_registry()


def test_plugin_api_version_is_stable():
    assert PLUGIN_API_VERSION == 1


def test_list_pipelines_includes_bundled_pymupdf():
    assert "pymupdf" in list_ingest_pipelines()
    descriptor = describe_ingest_pipeline("pymupdf")
    assert descriptor.provider == "pymupdf"
    assert descriptor.spec == "pymupdf"
    assert any(item.spec == "pymupdf" for item in list_ingest_pipeline_descriptors())


def test_unknown_parser_names_installed_providers(tmp_path):
    pdf = tmp_path / "manual.pdf"
    make_pdf(pdf)
    with pytest.raises(UnknownIngestPipelineError, match="tika"):
        convert(str(pdf), str(tmp_path / "out.vera"), parser="tika")


def test_registered_plugin_convert_is_dispatched(tmp_path):
    pdf = tmp_path / "manual.pdf"
    output = tmp_path / "plugin.vera"
    make_pdf(pdf)
    captured: dict[str, object] = {}

    def factory(variant: str):
        def ingest(source_path: str, output_path: str, **options):
            captured["variant"] = variant
            captured["source"] = source_path
            captured["options"] = options
            return convert(source_path, output_path, parser="pymupdf", **{
                key: value for key, value in options.items() if key != "parser"
            })

        return ingest

    register_ingest_pipeline("echo", factory, replace=True)
    register_ingest_pipeline_descriptor(
        "echo",
        lambda variant: PipelineDescriptor(
            provider="echo",
            variant=variant,
            spec="echo",
            label="echo",
            installed=True,
        ),
        replace=True,
    )

    result = convert(str(pdf), str(output), parser="echo", model="hashing", chunk_size=400)
    assert Path(result).is_file()
    assert captured["source"] == str(pdf)
    assert captured["options"]["chunk_size"] == 400
    pipeline = get_ingest_pipeline("echo")
    assert callable(pipeline)


def test_entry_points_discover_dist_info_plugin(tmp_path, monkeypatch):
    from importlib.metadata import entry_points

    (tmp_path / "echo_ingest_plugin.py").write_text(
        "from vera_ingest.pipeline import PipelineDescriptor\n"
        "def create_pipeline(variant=''):\n"
        "    return lambda source_path, output_path, **options: output_path\n"
        "def create_descriptor(variant=''):\n"
        "    return PipelineDescriptor(provider='echo', spec='echo', label='echo', installed=True)\n",
        encoding="utf-8",
    )
    dist = tmp_path / "echo_ingest_plugin-0.0.1.dist-info"
    dist.mkdir()
    (dist / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: echo-ingest-plugin\nVersion: 0.0.1\n",
        encoding="utf-8",
    )
    (dist / "entry_points.txt").write_text(
        "[vera.ingest_pipelines]\n"
        "echo = echo_ingest_plugin:create_pipeline\n\n"
        "[vera.ingest_pipeline_descriptors]\n"
        "echo = echo_ingest_plugin:create_descriptor\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    if hasattr(entry_points, "cache_clear"):
        entry_points.cache_clear()
    reset_ingest_pipeline_registry()
    assert "echo" in list_ingest_pipelines()
    descriptor = describe_ingest_pipeline("echo")
    assert descriptor.provider == "echo"


def test_broken_entry_point_is_reported_without_hiding_pymupdf(monkeypatch):
    class Boom:
        name = "broken"

        def load(self):
            raise ImportError("missing plugin dependency")

    class Groups:
        def select(self, group):
            if group == "vera.ingest_pipelines":
                return [Boom()]
            return []

        def get(self, group, default=None):
            return self.select(group)

    monkeypatch.setattr("vera_ingest.pipeline.entry_points", lambda: Groups())
    reset_ingest_pipeline_registry()
    from vera_ingest.pipeline import list_ingest_pipeline_load_errors

    errors = list_ingest_pipeline_load_errors()
    assert any("broken" in entry for entry in errors)
    assert "pymupdf" in list_ingest_pipelines()
