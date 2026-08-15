from __future__ import annotations

import base64
import sys
from pathlib import Path

import numpy as np

from vera_app import plugin_runtime
from vera_app.plugin_host import PluginHost, PluginHostError
from vera_app.remote_embedder import RemoteEmbedder
from vera_app.runtime import (
    PLUGIN_HOST_PROTOCOL,
    fallback_bundled_descriptors,
    merge_pipeline_descriptors,
    parse_pipeline_provider,
    plugin_host_compatibility_error,
    plugin_host_spawn_env,
    probe_from_ping,
    should_route_to_external,
)
from vera_doc import list_embedding_providers
from vera_doc.embeddings import serialize_vector


def test_runtime_parses_providers_and_routes_external():
    assert parse_pipeline_provider("") == "pymupdf"
    assert parse_pipeline_provider("docling:hybrid") == "docling"
    assert should_route_to_external("pymupdf", ["pymupdf"]) is False
    assert should_route_to_external("docling", ["pymupdf"]) is True


def test_runtime_rejects_protocol_1_and_accepts_protocol_2():
    assert plugin_host_compatibility_error(
        {
            "protocol": 1,
            "plugin_api": 1,
            "vera_ingest_version": "0.3.0",
        }
    )
    assert (
        plugin_host_compatibility_error(
            {
                "protocol": PLUGIN_HOST_PROTOCOL,
                "plugin_api": 1,
                "vera_ingest_version": "0.3.0",
            }
        )
        is None
    )


def test_runtime_merges_bundled_over_external_duplicates():
    bundled = fallback_bundled_descriptors()
    external = [
        {**bundled[0], "source": "external", "label": "external pymupdf"},
        {
            "provider": "docling",
            "variant": "",
            "spec": "docling",
            "label": "docling",
            "description": "",
            "installed": True,
            "capabilities": {},
            "fields": [],
            "notes": [],
            "source": "external",
        },
    ]
    merged = merge_pipeline_descriptors(bundled, external)
    assert [item["provider"] for item in merged] == ["pymupdf", "docling"]
    assert merged[0]["source"] == "bundled"
    assert merged[1]["source"] == "external"


def test_probe_from_ping_includes_embedders_and_doc_version():
    probe = probe_from_ping(
        "/venv/bin/python",
        {
            "protocol": 2,
            "plugin_api": 1,
            "python": "3.12.3",
            "vera_ingest_version": "0.3.0",
            "vera_doc_version": "0.3.1",
        },
        pipelines=[{"provider": "docling"}],
        embedders=[{"provider": "openai"}],
    )
    assert probe["ok"] is True
    assert probe["vera_doc_version"] == "0.3.1"
    assert probe["embedders"] == [{"provider": "openai"}]


def test_plugin_host_spawn_env_sets_pythonpath_and_secrets():
    env = plugin_host_spawn_env(
        plugin_host_root="/app/plugin-host",
        artifacts_path="/models",
        extra_env={"HF_TOKEN": "hf_test", "OPENAI_API_KEY": "sk-test"},
    )
    assert env["PYTHONPATH"] == "/app/plugin-host"
    assert env["PYTHONUNBUFFERED"] == "1"
    assert env["PYTHONNOUSERSITE"] == "1"
    assert env["DOCLING_ARTIFACTS_PATH"] == "/models"
    assert env["HF_TOKEN"] == "hf_test"
    assert env["OPENAI_API_KEY"] == "sk-test"


class _FakeHost:
    def __init__(self, dimension: int = 8):
        self.dimension = dimension
        self.calls: list[dict] = []
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True

    def request(self, payload, timeout=None, cancel=None):
        self.calls.append({"payload": payload, "timeout": timeout, "cancel": cancel})
        action = payload["action"]
        if action == "embedder_info":
            return {
                "model_name": payload["model"],
                "dimension": self.dimension,
                "normalization": "l2",
            }
        if action == "embed":
            texts = payload["texts"]
            return {
                "vectors": [
                    base64.b64encode(
                        serialize_vector(np.ones(self.dimension, dtype=np.float32))
                    ).decode("ascii")
                    for _ in texts
                ],
                "dimension": self.dimension,
            }
        raise PluginHostError(f"unexpected {action}")


def test_remote_embedder_resolves_dimension_and_caches_query_vectors():
    host = _FakeHost(dimension=4)
    embedder = RemoteEmbedder(
        host, "openai:text-embedding-3-small", embedder_options={"batch_size": 8}
    )
    assert embedder.dimension == 4
    first = embedder.embed(["detention pond"])
    second = embedder.embed(["detention pond"])
    assert first[0].shape == (4,)
    assert np.allclose(first[0], second[0])
    embed_calls = [item for item in host.calls if item["payload"]["action"] == "embed"]
    assert len(embed_calls) == 1
    assert embed_calls[0]["payload"]["embedder_options"] == {"batch_size": 8}


def test_register_external_embedders_keeps_bundled_names(monkeypatch):
    plugin_runtime._teardown()
    plugin_runtime._bundled_embedders = set(list_embedding_providers())
    fake = _FakeHost()

    def fake_models(provider: str):
        return ()

    monkeypatch.setattr(plugin_runtime, "_host", fake)
    monkeypatch.setattr(plugin_runtime, "_models_for_provider", fake_models)
    plugin_runtime._register_external_embedders(
        [
            {
                "provider": "hashing",
                "label": "external hashing",
                "description": "",
                "installed": True,
                "fields": [],
            },
            {
                "provider": "openai",
                "label": "OpenAI",
                "description": "",
                "installed": True,
                "default_model_id": "text-embedding-3-small",
                "capabilities": {"requires_api_key": True, "credential_env": "OPENAI_API_KEY"},
                "fields": [],
            },
        ]
    )
    try:
        assert "hashing" not in plugin_runtime._registered_embedders
        assert "openai" in plugin_runtime._registered_embedders
        described = plugin_runtime.describe_merged_embedders()
        sources = {item["provider"]: item["source"] for item in described["providers"]}
        assert sources["hashing"] == "bundled"
        assert sources["openai"] == "external"
    finally:
        plugin_runtime._teardown()


def test_describe_merged_pipelines_updates_module_probe(monkeypatch):
    class _DescribeHost:
        def __init__(self) -> None:
            self.fail = False

        def request(self, payload, timeout=None, cancel=None):
            if self.fail:
                raise PluginHostError("host down")
            return {
                "pipelines": [
                    {
                        "provider": "docling",
                        "variant": "",
                        "spec": "docling",
                        "label": "docling",
                        "description": "",
                        "installed": True,
                        "capabilities": {},
                        "fields": [],
                        "notes": [],
                    }
                ],
                "load_errors": ["vera_openai: missing OPENAI_API_KEY"],
            }

    host = _DescribeHost()
    plugin_runtime._probe = {"ok": True, "executable": "/venv/bin/python"}
    monkeypatch.setattr(plugin_runtime, "_host", host)
    monkeypatch.setattr(plugin_runtime, "ready", lambda: True)
    described = plugin_runtime.describe_merged_pipelines()
    assert any(item.get("provider") == "docling" for item in described["pipelines"])
    assert plugin_runtime._probe["load_errors"] == ["vera_openai: missing OPENAI_API_KEY"]

    host.fail = True
    plugin_runtime.describe_merged_pipelines()
    assert plugin_runtime._probe["ok"] is False
    assert plugin_runtime._probe["executable"] == "/venv/bin/python"
    assert "host down" in plugin_runtime._probe["error"]


def test_wrap_convert_routes_external_parser(monkeypatch):
    local_calls = []
    forwarded = []

    def local(request, write_event=None, cancel=None):
        local_calls.append(request)
        return {"output": "local"}

    monkeypatch.setattr(plugin_runtime, "ready", lambda: True)
    monkeypatch.setattr(plugin_runtime, "_bundled_pipelines", {"pymupdf"})
    monkeypatch.setattr(
        plugin_runtime,
        "forward_convert",
        lambda action, request, write_event=None, cancel=None: (
            forwarded.append((action, request)) or {"output": "host"}
        ),
    )
    handler = plugin_runtime.wrap_convert(local, "convert")
    assert handler({"parser": "pymupdf", "input": "a.pdf"}) == {"output": "local"}
    assert handler({"parser": "docling", "input": "b.pdf"}) == {"output": "host"}
    assert local_calls[0]["parser"] == "pymupdf"
    assert forwarded[0][0] == "convert"


def test_plugin_host_client_ping_and_embed():
    host = PluginHost()
    host.configure(
        executable=sys.executable,
        plugin_host_root=str(Path(__file__).resolve().parents[1] / "src"),
    )
    try:
        ping = host.request({"action": "ping"}, timeout=30)
        assert ping["protocol"] == 2
        assert "hashing" in ping["embedders"]
        embedder = RemoteEmbedder(host, "hashing")
        vectors = embedder.embed(["stormwater detention"])
        assert embedder.dimension > 0
        assert vectors[0].shape == (embedder.dimension,)
    finally:
        host.stop()
