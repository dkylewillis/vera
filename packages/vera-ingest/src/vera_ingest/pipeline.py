"""Ingest pipeline registry and optional plugin discovery.

Built-in conversion uses the ``pymupdf`` provider. Additional parsers register
under the ``vera.ingest_pipelines`` and ``vera.ingest_pipeline_descriptors``
entry-point groups so CLI and desktop hosts can discover them at runtime.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from typing import Any

logger = logging.getLogger(__name__)

PLUGIN_API_VERSION = 1
_ENTRY_POINT_GROUP = "vera.ingest_pipelines"
_DESCRIPTOR_ENTRY_POINT_GROUP = "vera.ingest_pipeline_descriptors"

_REGISTRY_LOCK = threading.RLock()
_PIPELINE_FACTORIES: dict[str, Callable[[str], Any]] = {}
_DESCRIPTOR_FACTORIES: dict[str, Callable[[str], "PipelineDescriptor"]] = {}
_LOAD_ERRORS: list[str] = []
_ENTRY_POINTS_LOADED = False


class UnknownIngestPipelineError(ValueError):
    """Raised when a parser spec does not match an installed pipeline."""


@dataclass
class PipelineDescriptor:
    """Metadata describing an ingest pipeline for CLI and desktop discovery."""

    provider: str
    variant: str = ""
    spec: str = ""
    label: str = ""
    description: str = ""
    installed: bool = True
    capabilities: dict[str, Any] = field(default_factory=dict)
    fields: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        spec = self.spec or format_ingest_pipeline_spec(self.provider, self.variant)
        return {
            "provider": self.provider,
            "variant": self.variant,
            "spec": spec,
            "label": self.label or spec,
            "description": self.description,
            "installed": self.installed,
            "capabilities": dict(self.capabilities),
            "fields": list(self.fields),
            "notes": list(self.notes),
        }


def parse_ingest_pipeline_spec(spec: str) -> tuple[str, str]:
    """Split ``provider`` or ``provider:variant`` into normalized parts."""
    raw = (spec or "").strip().lower()
    if not raw:
        return "pymupdf", ""
    if ":" in raw:
        provider, variant = raw.split(":", 1)
        provider = provider.strip()
        variant = variant.strip()
        if not provider:
            raise UnknownIngestPipelineError("Ingest parser pipeline spec is empty.")
        return provider, variant
    return raw, ""


def format_ingest_pipeline_spec(provider: str, variant: str = "") -> str:
    key = (provider or "").strip().lower()
    normalized_variant = (variant or "").strip().lower()
    if not normalized_variant or normalized_variant == "default":
        return key
    return f"{key}:{normalized_variant}"


def register_ingest_pipeline(
    provider: str,
    factory: Callable[[str], Any],
    *,
    replace: bool = False,
) -> None:
    """Register a pipeline factory called with the requested variant."""
    if not callable(factory):
        raise TypeError("ingest pipeline factory must be callable")
    key = (provider or "").strip().lower()
    if not key:
        raise ValueError("ingest pipeline provider must be non-empty")
    with _REGISTRY_LOCK:
        if key in _PIPELINE_FACTORIES and not replace:
            raise ValueError(f"ingest pipeline provider {provider!r} is already registered")
        _PIPELINE_FACTORIES[key] = factory


def register_ingest_pipeline_descriptor(
    provider: str,
    factory: Callable[[str], PipelineDescriptor],
    *,
    replace: bool = False,
) -> None:
    """Register a descriptor factory called with the requested variant."""
    if not callable(factory):
        raise TypeError("ingest pipeline descriptor factory must be callable")
    key = (provider or "").strip().lower()
    if not key:
        raise ValueError("ingest pipeline provider must be non-empty")
    with _REGISTRY_LOCK:
        if key in _DESCRIPTOR_FACTORIES and not replace:
            raise ValueError(f"ingest pipeline descriptor for {provider!r} is already registered")
        _DESCRIPTOR_FACTORIES[key] = factory


def reset_ingest_pipeline_registry() -> None:
    """Drop discovered factories. Used by tests."""
    global _ENTRY_POINTS_LOADED
    with _REGISTRY_LOCK:
        _PIPELINE_FACTORIES.clear()
        _DESCRIPTOR_FACTORIES.clear()
        _LOAD_ERRORS.clear()
        _ENTRY_POINTS_LOADED = False


def list_ingest_pipeline_load_errors() -> list[str]:
    _ensure_entry_points_loaded()
    with _REGISTRY_LOCK:
        return list(_LOAD_ERRORS)


def _unknown_pipeline_message(spec: str, available: str) -> str:
    return (
        f"Unknown ingest parser pipeline {spec!r}. "
        f"Installed providers: {available}. "
        f"Install a plugin registered under the '{_ENTRY_POINT_GROUP}' "
        "entry-point group, or call register_ingest_pipeline()."
    )


def _safe_load_entry_point(entry: Any, provider: str, *, kind: str) -> Any | None:
    try:
        return entry.load()
    except Exception as exc:  # noqa: BLE001 - one broken plugin must not hide others
        message = f"Failed to load {kind} plugin {provider!r}: {exc!r}"
        logger.warning("%s", message)
        with _REGISTRY_LOCK:
            _LOAD_ERRORS.append(message)
        return None


def _collect_entry_point_factories(group: str, *, kind: str) -> list[tuple[str, Any]]:
    loaded: list[tuple[str, Any]] = []
    discovered_groups = entry_points()
    if hasattr(discovered_groups, "select"):
        discovered = list(discovered_groups.select(group=group))
    else:
        discovered = list(discovered_groups.get(group, []))  # type: ignore[union-attr]
    for entry in discovered:
        provider = str(getattr(entry, "name", "") or "").strip().lower()
        if not provider:
            continue
        factory = _safe_load_entry_point(entry, provider, kind=kind)
        if callable(factory):
            loaded.append((provider, factory))
    return loaded


def _ensure_entry_points_loaded() -> None:
    global _ENTRY_POINTS_LOADED
    with _REGISTRY_LOCK:
        if _ENTRY_POINTS_LOADED:
            return
    pipeline_factories = _collect_entry_point_factories(_ENTRY_POINT_GROUP, kind="ingest pipeline")
    descriptor_factories = _collect_entry_point_factories(
        _DESCRIPTOR_ENTRY_POINT_GROUP, kind="ingest pipeline descriptor"
    )
    with _REGISTRY_LOCK:
        if _ENTRY_POINTS_LOADED:
            return
        for provider, factory in pipeline_factories:
            _PIPELINE_FACTORIES.setdefault(provider, factory)
        for provider, factory in descriptor_factories:
            _DESCRIPTOR_FACTORIES.setdefault(provider, factory)
        _ENTRY_POINTS_LOADED = True


def list_ingest_pipelines() -> list[str]:
    """Return sorted installed provider names."""
    ensure_pymupdf_registered()
    _ensure_entry_points_loaded()
    with _REGISTRY_LOCK:
        return sorted(_PIPELINE_FACTORIES)


def generic_pipeline_descriptor(provider: str, variant: str = "") -> PipelineDescriptor:
    spec = format_ingest_pipeline_spec(provider, variant)
    return PipelineDescriptor(
        provider=provider,
        variant=variant,
        spec=spec,
        label=spec,
        description=f"Installed ingest pipeline {spec}.",
        installed=True,
    )


def describe_ingest_pipeline(spec: str = "pymupdf") -> PipelineDescriptor:
    """Return metadata for an installed pipeline without instantiating it."""
    ensure_pymupdf_registered()
    provider, variant = parse_ingest_pipeline_spec(spec)
    _ensure_entry_points_loaded()
    with _REGISTRY_LOCK:
        if provider not in _PIPELINE_FACTORIES:
            available = ", ".join(sorted(_PIPELINE_FACTORIES)) or "(none)"
            raise UnknownIngestPipelineError(_unknown_pipeline_message(spec, available))
        factory = _DESCRIPTOR_FACTORIES.get(provider)
    if factory is None:
        return generic_pipeline_descriptor(provider, variant)
    descriptor = factory(variant)
    if not isinstance(descriptor, PipelineDescriptor):
        raise TypeError(
            f"Ingest pipeline descriptor for {provider!r} must return PipelineDescriptor."
        )
    return descriptor


def list_ingest_pipeline_descriptors() -> list[PipelineDescriptor]:
    """Return descriptors for each installed provider using its default variant."""
    return [describe_ingest_pipeline(provider) for provider in list_ingest_pipelines()]


def get_ingest_pipeline(spec: str = "pymupdf") -> Any:
    """Resolve an installed pipeline factory result."""
    ensure_pymupdf_registered()
    provider, variant = parse_ingest_pipeline_spec(spec)
    _ensure_entry_points_loaded()
    with _REGISTRY_LOCK:
        factory = _PIPELINE_FACTORIES.get(provider)
        if factory is None:
            available = ", ".join(sorted(_PIPELINE_FACTORIES)) or "(none)"
            raise UnknownIngestPipelineError(_unknown_pipeline_message(spec, available))
    pipeline = factory(variant)
    if not (callable(pipeline) or callable(getattr(pipeline, "convert", None))):
        raise TypeError(
            f"Ingest pipeline provider {provider!r} returned an object that is "
            "neither callable nor has a convert() method."
        )
    return pipeline


def invoke_ingest_pipeline(
    pipeline: Any,
    source_path: str,
    output_path: str,
    **options: Any,
) -> str:
    """Call a pipeline callable or a legacy ``.convert()`` object."""
    convert_fn = getattr(pipeline, "convert", None)
    if callable(convert_fn) and not callable(pipeline):
        result = convert_fn(source_path, output_path, **options)
    else:
        result = pipeline(source_path, output_path, **options)
    if not isinstance(result, str) or not result:
        raise TypeError("ingest pipeline must return the output path string")
    return result


def pymupdf_pipeline_descriptor(variant: str = "") -> PipelineDescriptor:
    del variant
    return PipelineDescriptor(
        provider="pymupdf",
        variant="",
        spec="pymupdf",
        label="pymupdf — default PDF pipeline",
        description="Bundled PyMuPDF parser with selective Tesseract OCR.",
        installed=True,
        capabilities={"overlap_supported": True, "ocr_engine": "tesseract"},
        fields=[
            {"key": "chunk_size", "label": "Chunk size", "type": "integer", "default": 500},
            {"key": "overlap", "label": "Overlap", "type": "integer", "default": 75},
            {"key": "ocr_mode", "label": "OCR mode", "type": "string", "default": "auto"},
            {"key": "ocr_language", "label": "OCR language", "type": "string", "default": "eng"},
            {"key": "ocr_dpi", "label": "OCR DPI", "type": "integer", "default": 300},
        ],
    )


def create_pymupdf_pipeline(variant: str = "") -> Callable[..., str]:
    """Entry-point factory for the bundled PyMuPDF pipeline."""
    normalized = (variant or "").strip().lower()
    if normalized not in {"", "default"}:
        raise UnknownIngestPipelineError(
            f"Unknown PyMuPDF pipeline variant {variant!r}; use 'pymupdf'."
        )

    def ingest(source_path: str, output_path: str, **options: Any) -> str:
        from .convert import convert_with_pymupdf

        filtered = {
            key: value
            for key, value in options.items()
            if key in {
                "model",
                "chunk_size",
                "overlap",
                "store_original",
                "ocr_mode",
                "ocr_language",
                "ocr_dpi",
                "cancel",
            }
        }
        return convert_with_pymupdf(source_path, output_path, **filtered)

    return ingest


def create_pymupdf_descriptor(variant: str = "") -> PipelineDescriptor:
    return pymupdf_pipeline_descriptor(variant)


def ensure_pymupdf_registered(*, replace: bool = True) -> None:
    """Register the bundled pipeline without relying on package metadata."""
    register_ingest_pipeline("pymupdf", create_pymupdf_pipeline, replace=replace)
    register_ingest_pipeline_descriptor("pymupdf", create_pymupdf_descriptor, replace=replace)


def convert_options_from_mapping(values: Mapping[str, Any] | None) -> dict[str, Any]:
    """Pick known convert kwargs from a sidecar/plugin-host request mapping."""
    if not values:
        return {}
    keys = (
        "model",
        "chunk_size",
        "overlap",
        "store_original",
        "ocr_mode",
        "ocr_language",
        "ocr_dpi",
    )
    options: dict[str, Any] = {}
    for key in keys:
        if key in values and values[key] is not None:
            options[key] = values[key]
    return options
