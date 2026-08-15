"""Sidecar-owned plugin host: probe, register remote embedders, route convert."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from vera_app.cancellation import CancellationToken
from vera_app.plugin_host import PluginHost, PluginHostError, bind_request_cancel
from vera_app.remote_embedder import RemoteEmbedder
from vera_app.runtime import (
    PLUGIN_HOST_VALIDATE_TIMEOUT_S,
    descriptors_from_result,
    fallback_bundled_descriptors,
    keep_bundled_descriptors,
    merge_pipeline_descriptors,
    probe_from_ping,
    should_route_to_external,
)
from vera_app.types import Request, WriteEvent
from vera_doc import (
    clear_embedder_cache,
    list_embedding_provider_descriptors,
    list_embedding_providers,
    register_embedder,
    register_embedder_descriptor,
    register_embedder_models,
)
from vera_doc.embedder_descriptors import (
    EmbedderCapabilities,
    EmbedderDescriptor,
    EmbedderField,
    EmbedderFieldChoice,
    EmbeddingModelInfo,
)
from vera_doc.embeddings import unregister_embedder
from vera_ingest import list_ingest_pipeline_descriptors

_host = PluginHost()
_probe: dict[str, Any] = {"ok": False}
_bundled_pipelines: set[str] = {"pymupdf"}
_bundled_embedders: set[str] = set()
_registered_embedders: set[str] = set()
_ready = False


def status() -> dict[str, Any]:
    return dict(_probe)


def ready() -> bool:
    return _ready and bool(_probe.get("ok"))


def bundled_pipeline_providers() -> set[str]:
    return set(_bundled_pipelines)


def should_route_convert(parser: str | None) -> bool:
    return ready() and should_route_to_external(parser, _bundled_pipelines)


def configure(request: Request) -> dict[str, Any]:
    global _probe, _ready
    enabled = bool(request.get("enabled"))
    executable = str(request.get("executable") or "").strip()
    artifacts = str(request.get("artifacts_path") or "").strip()
    plugin_host_root = str(request.get("plugin_host_root") or "").strip()
    extra_env = request.get("extra_env")
    env = (
        {str(key): str(value) for key, value in extra_env.items() if str(value).strip()}
        if isinstance(extra_env, dict)
        else {}
    )
    if not enabled or not executable:
        _teardown()
        _probe = {"ok": False, "error": "External Python is not configured."}
        _ready = False
        return status()
    if not plugin_host_root:
        _teardown()
        _probe = {"ok": False, "executable": executable, "error": "Plugin host root is missing."}
        _ready = False
        return status()
    _host.configure(
        executable=executable,
        plugin_host_root=plugin_host_root,
        artifacts_path=artifacts,
        extra_env=env,
    )
    try:
        ping = _host.request({"action": "ping"}, timeout=PLUGIN_HOST_VALIDATE_TIMEOUT_S)
        described = _host.request(
            {"action": "describe_ingest_pipelines"},
            timeout=PLUGIN_HOST_VALIDATE_TIMEOUT_S,
        )
        embedder_described = _host.request(
            {"action": "describe_embedding_providers"},
            timeout=PLUGIN_HOST_VALIDATE_TIMEOUT_S,
        )
    except Exception as exc:
        _teardown()
        _probe = {
            "ok": False,
            "executable": executable,
            "error": str(exc) or "Unable to start the plugin host",
        }
        _ready = False
        return status()
    pipelines = descriptors_from_result(described, "external")
    embedders = _normalize_embedder_descriptors(embedder_described.get("providers"), "external")
    _probe = probe_from_ping(executable, ping, pipelines, embedders)
    if described.get("load_errors") and isinstance(described.get("load_errors"), list):
        _probe["load_errors"] = [str(item) for item in described["load_errors"]]
    if not _probe["ok"]:
        _teardown()
        _ready = False
        return status()
    _register_external_embedders(embedders)
    _ready = True
    return status()


def describe_merged_pipelines() -> dict[str, Any]:
    local = [item.as_dict() for item in list_ingest_pipeline_descriptors()]
    bundled = keep_bundled_descriptors(local) or fallback_bundled_descriptors()
    global _bundled_pipelines, _probe
    _bundled_pipelines = {
        str(item.get("provider") or "pymupdf").strip().lower() for item in bundled
    }
    external: list[dict[str, Any]] = []
    if ready():
        try:
            described = _host.request({"action": "describe_ingest_pipelines"})
            external = descriptors_from_result(described, "external")
            load_errors = described.get("load_errors")
            if isinstance(load_errors, list):
                _probe["load_errors"] = [str(item) for item in load_errors]
                _probe["pipelines"] = external
        except Exception as exc:
            _probe = {
                "ok": False,
                "executable": _probe.get("executable"),
                "error": str(exc) or "External plugin host failed",
            }
    return {"pipelines": merge_pipeline_descriptors(bundled, external)}


def list_merged_pipelines() -> dict[str, Any]:
    described = describe_merged_pipelines()
    return {
        "pipelines": [
            str(item.get("spec") or item.get("provider")) for item in described.get("pipelines", [])
        ]
    }


def describe_merged_embedders() -> dict[str, Any]:
    providers: list[dict[str, Any]] = []
    for descriptor in list_embedding_provider_descriptors():
        item = descriptor.as_dict()
        provider = str(item.get("provider") or "").strip().lower()
        item["source"] = "external" if provider in _registered_embedders else "bundled"
        providers.append(item)
    return {"providers": providers}


def list_merged_embedder_names() -> dict[str, Any]:
    return {"providers": list_embedding_providers()}


def forward_convert(
    action: str,
    request: Request,
    write_event: WriteEvent | None = None,
    cancel: CancellationToken | None = None,
) -> dict[str, Any]:
    def _emit(event: dict[str, Any]) -> None:
        if write_event:
            write_event({key: value for key, value in event.items() if key != "id"})

    return _host.request(
        {key: value for key, value in request.items() if key != "id"} | {"action": action},
        cancel=cancel,
        on_event=_emit,
    )


def stop() -> None:
    _teardown()


def _teardown() -> None:
    global _ready
    _ready = False
    for provider in list(_registered_embedders):
        unregister_embedder(provider)
    _registered_embedders.clear()
    clear_embedder_cache()
    _host.stop()


def _register_external_embedders(embedders: list[dict[str, Any]]) -> None:
    global _bundled_embedders
    if not _bundled_embedders:
        _bundled_embedders = set(list_embedding_providers())
    for provider in list(_registered_embedders):
        unregister_embedder(provider)
    _registered_embedders.clear()
    clear_embedder_cache()
    for item in embedders:
        provider = str(item.get("provider") or "").strip().lower()
        if not provider or provider in _bundled_embedders:
            continue
        descriptor = _descriptor_from_mapping(item)
        models = _models_for_provider(provider)

        def factory(model_id: str, *, _provider: str = provider, **config: Any) -> RemoteEmbedder:
            spec = f"{_provider}:{model_id}" if model_id else _provider
            return RemoteEmbedder(_host, spec, embedder_options=config)

        def descriptor_factory(
            *, _descriptor: EmbedderDescriptor = descriptor
        ) -> EmbedderDescriptor:
            return _descriptor

        def model_factory(
            *,
            _models: tuple[EmbeddingModelInfo, ...] = models,
        ) -> tuple[EmbeddingModelInfo, ...]:
            return _models

        register_embedder(provider, factory, replace=True)
        register_embedder_descriptor(provider, descriptor_factory, replace=True)
        register_embedder_models(provider, model_factory, replace=True)
        _registered_embedders.add(provider)


def _normalize_embedder_descriptors(raw: Any, source: str) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        provider = str(item.get("provider") or "").strip().lower()
        if not provider:
            continue
        payload = dict(item)
        payload["provider"] = provider
        payload["source"] = source
        normalized.append(payload)
    return normalized


def _descriptor_from_mapping(raw: dict[str, Any]) -> EmbedderDescriptor:
    capabilities_raw = raw.get("capabilities")
    capabilities = EmbedderCapabilities()
    if isinstance(capabilities_raw, dict):
        capabilities = EmbedderCapabilities(
            requires_network=bool(capabilities_raw.get("requires_network", False)),
            requires_api_key=bool(capabilities_raw.get("requires_api_key", False)),
            credential_env=str(capabilities_raw.get("credential_env") or ""),
            local_model=bool(capabilities_raw.get("local_model", True)),
            configurable_dimension=bool(capabilities_raw.get("configurable_dimension", False)),
            supports_model_listing=bool(capabilities_raw.get("supports_model_listing", False)),
        )
    fields: list[EmbedderField] = []
    for item in raw.get("fields") or []:
        if not isinstance(item, dict) or not item.get("key"):
            continue
        choices = tuple(
            EmbedderFieldChoice(
                value=str(choice.get("value")),
                label=str(choice.get("label") or choice.get("value")),
            )
            for choice in item.get("choices") or []
            if isinstance(choice, dict) and choice.get("value") is not None
        )
        fields.append(
            EmbedderField(
                key=str(item["key"]),
                label=str(item.get("label") or item["key"]),
                type=item.get("type") or "string",
                default=item.get("default"),
                description=str(item.get("description") or ""),
                unit=item.get("unit"),
                choices=choices,
                minimum=item.get("minimum"),
                maximum=item.get("maximum"),
                step=item.get("step"),
                placeholder=item.get("placeholder"),
                allow_custom=bool(item.get("allow_custom", False)),
                allow_empty=bool(item.get("allow_empty", False)),
                scope=item.get("scope") or "convert",
            )
        )
    notes = raw.get("notes")
    examples = raw.get("example_specs")
    return EmbedderDescriptor(
        provider=str(raw.get("provider") or ""),
        label=str(raw.get("label") or raw.get("provider") or ""),
        description=str(raw.get("description") or ""),
        installed=raw.get("installed") is not False,
        default_model_id=str(raw.get("default_model_id") or ""),
        example_specs=tuple(str(item) for item in examples) if isinstance(examples, list) else (),
        capabilities=capabilities,
        fields=tuple(fields),
        notes=tuple(str(item) for item in notes) if isinstance(notes, list) else (),
    )


def _models_for_provider(provider: str) -> tuple[EmbeddingModelInfo, ...]:
    try:
        result = _host.request({"action": "list_embedding_models", "provider": provider})
    except PluginHostError:
        return ()
    models = result.get("models")
    if not isinstance(models, list):
        return ()
    parsed: list[EmbeddingModelInfo] = []
    for item in models:
        if not isinstance(item, dict) or not item.get("model_id"):
            continue
        parsed.append(
            EmbeddingModelInfo(
                model_id=str(item["model_id"]),
                label=str(item.get("label") or item["model_id"]),
                spec=str(item.get("spec") or f"{provider}:{item['model_id']}"),
                description=str(item.get("description") or ""),
            )
        )
    return tuple(parsed)


def handle_configure_plugin_runtime(request: Request) -> dict[str, Any]:
    return configure(request)


def handle_plugin_runtime_status(_request: Request) -> dict[str, Any]:
    return status()


def wrap_convert(
    local: Callable[..., Any],
    action: str,
) -> Callable[..., Any]:
    def handler(
        request: Request,
        write_event: WriteEvent | None = None,
        cancel: CancellationToken | None = None,
    ) -> Any:
        parser = str(request.get("parser") or "pymupdf")
        with bind_request_cancel(cancel):
            if should_route_convert(parser):
                return forward_convert(action, request, write_event=write_event, cancel=cancel)
            return local(request, write_event=write_event, cancel=cancel)

    return handler
