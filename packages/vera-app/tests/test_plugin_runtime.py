from __future__ import annotations

import base64
import sys
from pathlib import Path

import numpy as np
import pytest

from vera_app import plugin_runtime
from vera_app.cancellation import CancellationToken
from vera_app.plugin_host import PluginHost, PluginHostError, current_request_cancel
from vera_app.remote_embedder import RemoteEmbedder
from vera_app.runtime import (
    PLUGIN_HOST_PROTOCOL,
    descriptors_from_result,
    fallback_bundled_descriptors,
    merge_pipeline_descriptors,
    normalize_pipeline_descriptor,
    parse_pipeline_provider,
    parse_version_parts,
    plugin_host_compatibility_error,
    plugin_host_spawn_env,
    probe_from_ping,
    should_route_to_external,
)
from vera_doc import describe_embedder, list_embedding_models, list_embedding_providers
from vera_doc.embeddings import serialize_vector

COMPATIBLE_PING = {
    "protocol": PLUGIN_HOST_PROTOCOL,
    "plugin_api": 1,
    "python": "3.12.3",
    "vera_ingest_version": "0.3.0",
    "vera_doc_version": "0.3.1",
}


@pytest.fixture
def isolated_plugin_runtime():
    plugin_runtime._teardown()
    plugin_runtime._bundled_embedders = set()
    plugin_runtime._bundled_pipelines = {"pymupdf"}
    plugin_runtime._probe = {"ok": False}
    yield
    plugin_runtime._teardown()
    plugin_runtime._bundled_embedders = set()
    plugin_runtime._bundled_pipelines = {"pymupdf"}
    plugin_runtime._probe = {"ok": False}


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


def test_runtime_rejects_missing_and_incompatible_ingest_versions():
    missing = plugin_host_compatibility_error({"protocol": PLUGIN_HOST_PROTOCOL, "plugin_api": 1})
    assert missing is not None
    assert "vera-ingest version" in missing
    wrong_minor = plugin_host_compatibility_error(
        {
            "protocol": PLUGIN_HOST_PROTOCOL,
            "plugin_api": 1,
            "vera_ingest_version": "0.2.5",
        }
    )
    assert wrong_minor is not None
    assert "0.2.5" in wrong_minor
    assert parse_version_parts("0.3.1") == (0, 3)
    assert parse_version_parts("not-a-version") is None
    assert parse_version_parts("1") is None


def test_descriptors_from_result_falls_back_for_bundled_and_skips_junk():
    bundled = descriptors_from_result({"pipelines": []}, "bundled")
    assert bundled[0]["provider"] == "pymupdf"
    assert bundled[0]["source"] == "bundled"
    assert descriptors_from_result(None, "external") == []
    assert descriptors_from_result({"pipelines": [None, "x", {}]}, "external") == []
    assert (
        normalize_pipeline_descriptor({"provider": "Docling"}, "external")["provider"] == "docling"
    )
    assert normalize_pipeline_descriptor({}, "external") is None


def test_plugin_host_spawn_env_clears_stale_artifacts_path():
    env = plugin_host_spawn_env(
        plugin_host_root="/app/plugin-host",
        artifacts_path="  ",
        extra_env={"DOCLING_ARTIFACTS_PATH": "stale-cache"},
    )
    assert env["PYTHONPATH"] == "/app/plugin-host"
    assert "DOCLING_ARTIFACTS_PATH" not in env


class _ScriptedHost:
    def __init__(self, ping=None, fail=None):
        self.configured = None
        self.stopped = False
        self.fail = fail
        self.ping = dict(ping or COMPATIBLE_PING)
        self.calls: list[dict] = []

    def configure(self, **kwargs):
        self.configured = kwargs

    def stop(self) -> None:
        self.stopped = True

    def request(self, payload, timeout=None, cancel=None):
        self.calls.append({"payload": payload, "timeout": timeout, "cancel": cancel})
        if self.fail:
            raise PluginHostError(self.fail)
        action = payload["action"]
        if action == "ping":
            return self.ping
        if action == "describe_ingest_pipelines":
            return {
                "pipelines": [
                    {
                        "provider": "docling",
                        "spec": "docling",
                        "label": "docling",
                        "installed": True,
                    }
                ],
                "load_errors": ["vera_openai: missing OPENAI_API_KEY"],
            }
        if action == "describe_embedding_providers":
            return {
                "providers": [
                    "not-a-mapping",
                    {"provider": "  "},
                    {
                        "provider": "hashing",
                        "label": "external hashing",
                        "installed": True,
                        "fields": [],
                    },
                    {
                        "provider": "unit-test-remote",
                        "label": "Unit Test Remote",
                        "description": "Remote embeddings",
                        "installed": True,
                        "default_model_id": "text-embedding-3-small",
                        "capabilities": {
                            "requires_api_key": True,
                            "credential_env": "OPENAI_API_KEY",
                            "local_model": False,
                        },
                        "fields": [
                            {
                                "key": "batch_size",
                                "label": "Batch size",
                                "type": "integer",
                                "default": 16,
                                "minimum": 1,
                                "choices": [{"value": 8, "label": "8"}],
                            },
                            {"label": "missing key"},
                        ],
                        "notes": ["needs a key"],
                    },
                ]
            }
        if action == "list_embedding_models":
            provider = payload["provider"]
            return {
                "models": [
                    {
                        "model_id": "text-embedding-3-small",
                        "label": "small",
                        "spec": f"{provider}:text-embedding-3-small",
                    },
                    {"label": "missing id"},
                ]
            }
        raise PluginHostError(f"unexpected {action}")


def test_configure_disabled_or_incomplete_does_not_start_host(isolated_plugin_runtime, monkeypatch):
    host = _ScriptedHost()
    monkeypatch.setattr(plugin_runtime, "_host", host)
    disabled = plugin_runtime.configure({"enabled": False, "executable": "/venv/bin/python"})
    assert disabled["ok"] is False
    assert "not configured" in disabled["error"]
    assert host.configured is None

    missing_root = plugin_runtime.configure(
        {"enabled": True, "executable": "/venv/bin/python", "plugin_host_root": "  "}
    )
    assert missing_root["ok"] is False
    assert "Plugin host root is missing" in missing_root["error"]
    assert missing_root["executable"] == "/venv/bin/python"
    assert host.configured is None
    assert plugin_runtime.ready() is False


def test_configure_omits_blank_extra_env_and_registers_external_embedder(
    isolated_plugin_runtime, monkeypatch
):
    host = _ScriptedHost()
    monkeypatch.setattr(plugin_runtime, "_host", host)
    status = plugin_runtime.configure(
        {
            "enabled": True,
            "executable": "/venv/bin/python",
            "plugin_host_root": "/app/plugin-host",
            "artifacts_path": "/models",
            "extra_env": {"OPENAI_API_KEY": "sk-test", "HF_TOKEN": "  ", "EMPTY": ""},
        }
    )
    assert status["ok"] is True
    assert plugin_runtime.ready() is True
    assert host.configured["executable"] == "/venv/bin/python"
    assert host.configured["extra_env"] == {"OPENAI_API_KEY": "sk-test"}
    assert host.configured["artifacts_path"] == "/models"
    assert status["load_errors"] == ["vera_openai: missing OPENAI_API_KEY"]
    assert "unit-test-remote" in plugin_runtime._registered_embedders
    assert "hashing" not in plugin_runtime._registered_embedders
    descriptor = describe_embedder("unit-test-remote")
    assert descriptor.capabilities.credential_env == "OPENAI_API_KEY"
    assert descriptor.fields[0].key == "batch_size"
    assert descriptor.fields[0].choices[0].value == "8"
    models = list_embedding_models("unit-test-remote")
    assert [item.model_id for item in models] == ["text-embedding-3-small"]
    merged = plugin_runtime.list_merged_pipelines()
    assert "pymupdf" in merged["pipelines"]
    assert "docling" in merged["pipelines"]


def test_configure_incompatible_probe_does_not_register_embedders(
    isolated_plugin_runtime, monkeypatch
):
    host = _ScriptedHost(ping={**COMPATIBLE_PING, "vera_ingest_version": "0.2.5"})
    monkeypatch.setattr(plugin_runtime, "_host", host)
    status = plugin_runtime.configure(
        {
            "enabled": True,
            "executable": "/venv/bin/python",
            "plugin_host_root": "/app/plugin-host",
        }
    )
    assert status["ok"] is False
    assert "0.2.5" in status["error"]
    assert plugin_runtime.ready() is False
    assert plugin_runtime._registered_embedders == set()
    assert host.stopped is True


def test_configure_host_failure_returns_error_probe(isolated_plugin_runtime, monkeypatch):
    host = _ScriptedHost(fail="unable to spawn")
    monkeypatch.setattr(plugin_runtime, "_host", host)
    status = plugin_runtime.configure(
        {
            "enabled": True,
            "executable": "/venv/bin/python",
            "plugin_host_root": "/app/plugin-host",
        }
    )
    assert status["ok"] is False
    assert "unable to spawn" in status["error"]
    assert plugin_runtime.ready() is False


def test_remote_embedder_rejects_mismatched_vector_payload():
    class _BadHost(_FakeHost):
        def request(self, payload, timeout=None, cancel=None):
            if payload["action"] == "embed":
                return {"vectors": []}
            return super().request(payload, timeout=timeout, cancel=cancel)

    embedder = RemoteEmbedder(_BadHost(), "openai:text-embedding-3-small")
    with pytest.raises(RuntimeError, match="unexpected vector payload"):
        embedder.embed(["detention pond"])


def test_wrap_convert_stays_local_when_runtime_not_ready(monkeypatch):
    local_calls = []
    forwarded = []

    def local(request, write_event=None, cancel=None):
        local_calls.append(current_request_cancel())
        return {"output": "local"}

    monkeypatch.setattr(plugin_runtime, "ready", lambda: False)
    monkeypatch.setattr(
        plugin_runtime,
        "forward_convert",
        lambda action, request, write_event=None, cancel=None: (
            forwarded.append(action) or {"output": "host"}
        ),
    )
    token = CancellationToken()
    handler = plugin_runtime.wrap_convert(local, "convert")
    assert handler({"parser": "docling", "input": "b.pdf"}, cancel=token) == {"output": "local"}
    assert forwarded == []
    assert local_calls == [token]


def test_models_for_provider_returns_empty_on_host_error(monkeypatch):
    class _FailingHost:
        def request(self, payload, timeout=None, cancel=None):
            raise PluginHostError("host down")

    monkeypatch.setattr(plugin_runtime, "_host", _FailingHost())
    assert plugin_runtime._models_for_provider("openai") == ()
