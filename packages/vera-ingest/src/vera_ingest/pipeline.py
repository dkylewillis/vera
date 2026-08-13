from __future__ import annotations

import threading
from collections.abc import Callable
from importlib.metadata import entry_points
from typing import Any

from .descriptors import PipelineDescriptor, generic_pipeline_descriptor
from .types import IngestRequest, IngestResult

_ENTRY_POINT_GROUP = "vera.ingest_pipelines"
_DESCRIPTOR_ENTRY_POINT_GROUP = "vera.ingest_pipeline_descriptors"
_REGISTRY_LOCK = threading.RLock()
_PIPELINE_FACTORIES: dict[str, Callable[[str], "IngestPipeline"]] = {}
_DESCRIPTOR_FACTORIES: dict[str, Callable[[str], PipelineDescriptor]] = {}
_PIPELINE_CACHE: dict[tuple[str, str], "IngestPipeline"] = {}
_ENTRY_POINTS_LOADED = False
_DEFAULT_VARIANTS = {"docling": "hybrid"}


IngestPipeline = Callable[[str, IngestRequest], IngestResult]
"""A pipeline that normalizes a source document into an ingest bundle.

A pipeline is any callable matching this signature — a plain function, or an
object implementing ``__call__`` if it needs to hold state. There is no base
class to inherit from::

    def create_pipeline(variant: str = "") -> IngestPipeline:
        def ingest(source_path: str, options: IngestRequest) -> IngestResult:
            ...
        return ingest

For compatibility with pre-0.3.x plugins, an object exposing a callable
``ingest(self, source_path, options)`` method is also accepted; see
:func:`invoke_ingest_pipeline`.
"""


def invoke_ingest_pipeline(
    pipeline: IngestPipeline, source_path: str, request: IngestRequest
) -> IngestResult:
    """Call ``pipeline``, accepting both a bare callable and a legacy ``.ingest()`` object."""
    ingest = getattr(pipeline, "ingest", None)
    if callable(ingest):
        return ingest(source_path, request)
    return pipeline(source_path, request)


class UnknownIngestPipelineError(ValueError):
    """Raised when an ingest pipeline spec cannot be resolved."""


def _normalize_provider(provider: str) -> str:
    key = provider.strip().lower()
    if not key:
        raise ValueError("ingest pipeline provider name must be non-empty")
    if ":" in key:
        raise ValueError("ingest pipeline provider name must not contain ':'")
    return key


def parse_ingest_pipeline_spec(spec: str | None) -> tuple[str, str]:
    """Resolve ``provider[:variant]`` into normalized components."""
    normalized = (spec or "pymupdf").strip().lower()
    if not normalized:
        normalized = "pymupdf"
    provider, separator, variant = normalized.partition(":")
    provider = provider.strip()
    variant = variant.strip()
    if not provider or (separator and not variant):
        raise UnknownIngestPipelineError(
            f"Invalid ingest pipeline spec {spec!r}; expected 'provider[:variant]'."
        )
    if not separator:
        variant = _DEFAULT_VARIANTS.get(provider, "")
    return provider, variant


def format_ingest_pipeline_spec(provider: str, variant: str = "") -> str:
    """Build a canonical ``provider[:variant]`` spec string."""
    key = _normalize_provider(provider)
    normalized_variant = (variant or "").strip().lower()
    if not normalized_variant or normalized_variant == "default":
        return key
    return f"{key}:{normalized_variant}"


def register_ingest_pipeline(
    provider: str,
    factory: Callable[[str], IngestPipeline] | None = None,
    *,
    replace: bool = False,
) -> Callable[[Callable[[str], IngestPipeline]], Callable[[str], IngestPipeline]] | None:
    """Register a provider factory called with the requested variant.

    Called with both arguments, this registers ``factory`` immediately and
    returns ``None``, as before. Omit ``factory`` to use it as a decorator
    instead — handy for local experiments, notebooks, and tests that would
    otherwise need a separate factory function and a separate call::

        @register_ingest_pipeline("myexperiment")
        def create_pipeline(variant: str = "") -> IngestPipeline:
            return MyPipeline()
    """
    if factory is None:
        def decorator(
            actual_factory: Callable[[str], IngestPipeline],
        ) -> Callable[[str], IngestPipeline]:
            register_ingest_pipeline(provider, actual_factory, replace=replace)
            return actual_factory

        return decorator

    key = _normalize_provider(provider)
    if not callable(factory):
        raise TypeError("ingest pipeline factory must be callable")
    with _REGISTRY_LOCK:
        if key in _PIPELINE_FACTORIES and not replace:
            raise ValueError(f"ingest pipeline provider {provider!r} is already registered")
        _PIPELINE_FACTORIES[key] = factory
        for cache_key in tuple(_PIPELINE_CACHE):
            if cache_key[0] == key:
                _PIPELINE_CACHE.pop(cache_key, None)
    return None


def register_ingest_pipeline_descriptor(
    provider: str,
    factory: Callable[[str], PipelineDescriptor] | None = None,
    *,
    replace: bool = False,
) -> Callable[[Callable[[str], PipelineDescriptor]], Callable[[str], PipelineDescriptor]] | None:
    """Register a descriptor factory called with the requested variant.

    Also usable as a decorator when ``factory`` is omitted — see
    :func:`register_ingest_pipeline`.
    """
    if factory is None:
        def decorator(
            actual_factory: Callable[[str], PipelineDescriptor],
        ) -> Callable[[str], PipelineDescriptor]:
            register_ingest_pipeline_descriptor(provider, actual_factory, replace=replace)
            return actual_factory

        return decorator

    key = _normalize_provider(provider)
    if not callable(factory):
        raise TypeError("ingest pipeline descriptor factory must be callable")
    with _REGISTRY_LOCK:
        if key in _DESCRIPTOR_FACTORIES and not replace:
            raise ValueError(
                f"ingest pipeline descriptor for {provider!r} is already registered"
            )
        _DESCRIPTOR_FACTORIES[key] = factory
    return None


def _load_entry_point_group(group: str) -> list[Any]:
    try:
        selected = entry_points(group=group)
    except TypeError:  # pragma: no cover - Python <3.10 compatibility path
        selected = entry_points().get(group, [])  # type: ignore[index]
    return list(selected)


def _ensure_entry_points_loaded() -> None:
    global _ENTRY_POINTS_LOADED
    with _REGISTRY_LOCK:
        if _ENTRY_POINTS_LOADED:
            return
        for entry in _load_entry_point_group(_ENTRY_POINT_GROUP):
            provider = entry.name.strip().lower()
            if not provider or provider in _PIPELINE_FACTORIES:
                continue
            try:
                factory = entry.load()
            except Exception:  # noqa: BLE001, S112 - one broken plugin must not hide others
                continue
            if callable(factory):
                _PIPELINE_FACTORIES[provider] = factory
        for entry in _load_entry_point_group(_DESCRIPTOR_ENTRY_POINT_GROUP):
            provider = entry.name.strip().lower()
            if not provider or provider in _DESCRIPTOR_FACTORIES:
                continue
            try:
                factory = entry.load()
            except Exception:  # noqa: BLE001, S112
                continue
            if callable(factory):
                _DESCRIPTOR_FACTORIES[provider] = factory
        _ENTRY_POINTS_LOADED = True


def get_ingest_pipeline(spec: str = "pymupdf") -> IngestPipeline:
    """Resolve and cache an installed pipeline.

    Resolution is strict: an unknown provider or variant raises instead of
    falling back to another installed pipeline.
    """
    provider, variant = parse_ingest_pipeline_spec(spec)
    _ensure_entry_points_loaded()
    cache_key = (provider, variant)
    with _REGISTRY_LOCK:
        cached = _PIPELINE_CACHE.get(cache_key)
        if cached is not None:
            return cached
        factory = _PIPELINE_FACTORIES.get(provider)
        if factory is None:
            available = ", ".join(sorted(_PIPELINE_FACTORIES)) or "(none)"
            raise UnknownIngestPipelineError(
                f"Unknown ingest parser pipeline {spec!r}. "
                f"Installed providers: {available}. "
                f"Install vera-ingest-pymupdf for the default PDF pipeline, "
                f"another plugin registered under the '{_ENTRY_POINT_GROUP}' "
                "entry-point group, or call register_ingest_pipeline()."
            )
        pipeline = factory(variant)
        if not (callable(pipeline) or callable(getattr(pipeline, "ingest", None))):
            raise TypeError(
                f"Ingest pipeline provider {provider!r} returned an object that is "
                "neither callable nor has an ingest() method."
            )
        _PIPELINE_CACHE[cache_key] = pipeline
        return pipeline


def describe_ingest_pipeline(spec: str = "pymupdf") -> PipelineDescriptor:
    """Return metadata for an installed pipeline without instantiating it."""
    provider, variant = parse_ingest_pipeline_spec(spec)
    _ensure_entry_points_loaded()
    with _REGISTRY_LOCK:
        if provider not in _PIPELINE_FACTORIES:
            available = ", ".join(sorted(_PIPELINE_FACTORIES)) or "(none)"
            raise UnknownIngestPipelineError(
                f"Unknown ingest parser pipeline {spec!r}. "
                f"Installed providers: {available}. "
                f"Install vera-ingest-pymupdf for the default PDF pipeline, "
                f"another plugin registered under the '{_ENTRY_POINT_GROUP}' "
                "entry-point group, or call register_ingest_pipeline()."
            )
        factory = _DESCRIPTOR_FACTORIES.get(provider)
        if factory is None:
            return generic_pipeline_descriptor(provider, variant)
        descriptor = factory(variant)
        if not isinstance(descriptor, PipelineDescriptor):
            raise TypeError(
                f"Ingest pipeline descriptor for {provider!r} must return PipelineDescriptor."
            )
        return descriptor


def list_ingest_pipelines() -> list[str]:
    """Return sorted installed provider names."""
    _ensure_entry_points_loaded()
    with _REGISTRY_LOCK:
        return sorted(_PIPELINE_FACTORIES)


def list_ingest_pipeline_descriptors() -> list[PipelineDescriptor]:
    """Return descriptors for each installed provider using its default variant."""
    providers = list_ingest_pipelines()
    descriptors: list[PipelineDescriptor] = []
    for provider in providers:
        variant = _DEFAULT_VARIANTS.get(provider, "")
        spec = format_ingest_pipeline_spec(provider, variant)
        descriptors.append(describe_ingest_pipeline(spec))
    return descriptors


def clear_ingest_pipeline_cache() -> None:
    """Drop resolved pipeline instances."""
    with _REGISTRY_LOCK:
        _PIPELINE_CACHE.clear()


def reset_ingest_pipeline_registry(*, builtins: bool = True) -> None:
    """Reset registry and discovery state, primarily for tests.

    ``builtins`` is accepted for compatibility with older tests; pipelines are
    discovered only through entry points and explicit ``register_*`` calls.
    """
    del builtins  # retained for call-site compatibility
    global _ENTRY_POINTS_LOADED
    with _REGISTRY_LOCK:
        _PIPELINE_FACTORIES.clear()
        _DESCRIPTOR_FACTORIES.clear()
        _PIPELINE_CACHE.clear()
        _ENTRY_POINTS_LOADED = False


_TESSERACT_LEGACY_OPTION_KEYS = frozenset({"ocr_language", "ocr_dpi", "ocr_download"})


def _should_forward_legacy_key(key: str, descriptor: PipelineDescriptor) -> bool:
    """Tesseract-shaped convert()/CLI aliases stay on Tesseract pipelines."""
    if key not in _TESSERACT_LEGACY_OPTION_KEYS:
        return True
    return descriptor.capabilities.ocr_engine == "tesseract"


def prepare_pipeline_options(
    *,
    spec: str,
    pipeline_options: dict[str, Any] | None = None,
    legacy_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge legacy convert kwargs with explicit pipeline options.

    When a pipeline publishes descriptor fields, only those legacy keys are
    forwarded so PyMuPDF defaults such as ``overlap`` and ``ocr_dpi`` do not
    leak into plugins that omit them. Tesseract-shaped aliases
    (``ocr_language``, ``ocr_dpi``, ``ocr_download``) are forwarded only when
    ``capabilities.ocr_engine`` is ``"tesseract"``, so Docling/RapidOCR keeps
    its own ``ocr_language`` default instead of inheriting ``eng``.
    Undescribed plugins receive the remaining compatibility bag. Explicit
    ``pipeline_options`` always win.
    """
    descriptor = describe_ingest_pipeline(spec)
    allowed = descriptor.field_keys()
    merged: dict[str, Any] = {}
    legacy = legacy_options or {}
    if allowed:
        for key, value in legacy.items():
            if key in allowed and _should_forward_legacy_key(key, descriptor):
                merged[key] = value
    else:
        for key, value in legacy.items():
            if _should_forward_legacy_key(key, descriptor):
                merged[key] = value
    if pipeline_options:
        merged.update(pipeline_options)
    return merged
