"""Plugin-host compatibility, descriptor merge, and convert routing helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

BUNDLED_PIPELINE_PROVIDER = "pymupdf"
PLUGIN_HOST_PROTOCOL = 2
PLUGIN_API_VERSION = 1
COMPATIBLE_INGEST_MAJOR = 0
COMPATIBLE_INGEST_MINOR = 3
PLUGIN_HOST_VALIDATE_TIMEOUT_S = 120.0
PLUGIN_HOST_EMBED_TIMEOUT_S = 30.0


def parse_pipeline_provider(spec: str | None) -> str:
    raw = (spec or "").strip().lower()
    if not raw:
        return BUNDLED_PIPELINE_PROVIDER
    provider = raw.split(":", 1)[0].strip()
    return provider or BUNDLED_PIPELINE_PROVIDER


def is_bundled_pipeline(spec: str | None) -> bool:
    return parse_pipeline_provider(spec) == BUNDLED_PIPELINE_PROVIDER


def parse_version_parts(version: str | None) -> tuple[int, int] | None:
    if not version:
        return None
    text = version.strip()
    parts = text.split(".")
    if len(parts) < 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def plugin_host_compatibility_error(probe: Mapping[str, Any]) -> str | None:
    protocol = probe.get("protocol")
    if protocol != PLUGIN_HOST_PROTOCOL:
        return (
            f"Incompatible plugin host protocol {protocol if protocol is not None else '(missing)'}; "
            f"expected {PLUGIN_HOST_PROTOCOL}."
        )
    plugin_api = probe.get("plugin_api")
    if plugin_api != PLUGIN_API_VERSION:
        return (
            f"Incompatible ingest plugin API {plugin_api if plugin_api is not None else '(missing)'}; "
            f"expected {PLUGIN_API_VERSION}."
        )
    vera_ingest_version = (
        str(probe.get("vera_ingest_version")) if probe.get("vera_ingest_version") else None
    )
    parts = parse_version_parts(vera_ingest_version)
    if not parts:
        return "The selected Python environment did not report a vera-ingest version."
    major, minor = parts
    if major != COMPATIBLE_INGEST_MAJOR or minor != COMPATIBLE_INGEST_MINOR:
        return (
            f"vera-ingest {vera_ingest_version} is not compatible with this app "
            f"(requires {COMPATIBLE_INGEST_MAJOR}.{COMPATIBLE_INGEST_MINOR}.x)."
        )
    return None


def normalize_pipeline_descriptor(
    raw: Any,
    source: str,
) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    provider = str(raw.get("provider") or "").strip().lower()
    spec = str(raw.get("spec") or "").strip() or provider
    if not provider and not spec:
        return None
    notes = raw.get("notes")
    fields = raw.get("fields")
    capabilities = raw.get("capabilities")
    return {
        "provider": provider or parse_pipeline_provider(spec),
        "variant": str(raw.get("variant") or ""),
        "spec": spec or provider,
        "label": str(raw.get("label") or spec or provider),
        "description": str(raw.get("description") or ""),
        "installed": raw.get("installed") is not False,
        "capabilities": dict(capabilities) if isinstance(capabilities, Mapping) else {},
        "fields": [item for item in fields if isinstance(item, Mapping)] if isinstance(fields, list) else [],
        "notes": [str(item) for item in notes] if isinstance(notes, list) else [],
        "source": source,
    }


def keep_bundled_descriptors(descriptors: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for item in descriptors:
        spec = str(item.get("spec") or item.get("provider") or "")
        if is_bundled_pipeline(spec):
            kept.append({**dict(item), "source": "bundled"})
    return kept


def merge_pipeline_descriptors(
    bundled: Iterable[Mapping[str, Any]],
    external: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for descriptor in bundled:
        key = str(descriptor.get("provider") or parse_pipeline_provider(str(descriptor.get("spec") or "")))
        if key in seen:
            continue
        seen.add(key)
        merged.append({**dict(descriptor), "source": "bundled"})
    for descriptor in external:
        key = str(descriptor.get("provider") or parse_pipeline_provider(str(descriptor.get("spec") or "")))
        if key in seen:
            continue
        seen.add(key)
        merged.append({**dict(descriptor), "source": "external"})
    return merged


def should_route_to_external(parser: str | None, bundled_providers: Iterable[str]) -> bool:
    provider = parse_pipeline_provider(parser)
    bundled = {item.strip().lower() for item in bundled_providers if item and item.strip()}
    if not bundled:
        return not is_bundled_pipeline(provider)
    return provider not in bundled


def fallback_bundled_descriptors() -> list[dict[str, Any]]:
    return [
        {
            "provider": BUNDLED_PIPELINE_PROVIDER,
            "variant": "",
            "spec": BUNDLED_PIPELINE_PROVIDER,
            "label": "pymupdf — default PDF pipeline",
            "description": "Bundled PyMuPDF parser with selective Tesseract OCR.",
            "installed": True,
            "capabilities": {},
            "fields": [],
            "notes": [],
            "source": "bundled",
        }
    ]


def descriptors_from_result(result: Any, source: str) -> list[dict[str, Any]]:
    pipelines = result.get("pipelines") if isinstance(result, Mapping) else None
    if not isinstance(pipelines, list):
        return fallback_bundled_descriptors() if source == "bundled" else []
    normalized = [
        item
        for item in (normalize_pipeline_descriptor(raw, source) for raw in pipelines)
        if item is not None
    ]
    if source == "bundled" and not normalized:
        return fallback_bundled_descriptors()
    return normalized


def probe_from_ping(
    executable: str,
    result: Mapping[str, Any] | None,
    pipelines: list[dict[str, Any]] | None = None,
    embedders: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload = dict(result or {})
    load_errors = payload.get("load_errors")
    compatibility = plugin_host_compatibility_error(payload)
    return {
        "ok": compatibility is None,
        "executable": executable,
        "python_version": payload.get("python") if isinstance(payload.get("python"), str) else None,
        "vera_ingest_version": (
            payload.get("vera_ingest_version")
            if isinstance(payload.get("vera_ingest_version"), str)
            else None
        ),
        "vera_doc_version": (
            payload.get("vera_doc_version")
            if isinstance(payload.get("vera_doc_version"), str)
            else None
        ),
        "protocol": payload.get("protocol") if isinstance(payload.get("protocol"), int) else None,
        "plugin_api": payload.get("plugin_api") if isinstance(payload.get("plugin_api"), int) else None,
        "pipelines": pipelines or [],
        "embedders": embedders or [],
        "load_errors": (
            [str(item) for item in load_errors] if isinstance(load_errors, list) else []
        ),
        "error": compatibility,
    }


def plugin_host_spawn_env(
    *,
    plugin_host_root: str,
    artifacts_path: str = "",
    extra_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    env = {str(key): str(value) for key, value in dict(extra_env or {}).items()}
    env["PYTHONPATH"] = plugin_host_root
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    artifacts = artifacts_path.strip()
    if artifacts:
        env["DOCLING_ARTIFACTS_PATH"] = artifacts
    else:
        env.pop("DOCLING_ARTIFACTS_PATH", None)
    return env
