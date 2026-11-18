from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import Any

from .descriptors import PipelineDescriptor, generic_pipeline_descriptor
from .external import (
    ExternalPipelineError,
    configured_python,
    list_external_descriptors,
    resolve_python,
)
from .plugins import activate_plugin_dirs
from .types import IngestRequest, IngestResult

logger = logging.getLogger(__name__)

PLUGIN_API_VERSION = 1

_ENTRY_POINT_GROUP = "vera.ingest_pipelines"
_DESCRIPTOR_ENTRY_POINT_GROUP = "vera.ingest_pipeline_descriptors"
_REGISTRY_LOCK = threading.RLock()
_PIPELINE_FACTORIES: dict[str, Callable[[str], IngestPipeline]] = {}
_DESCRIPTOR_FACTORIES: dict[str, Callable[[str], PipelineDescriptor]] = {}
_PIPELINE_CACHE: dict[tuple[str, str], IngestPipeline] = {}
_DESCRIPTOR_CACHE: dict[tuple[str, str], PipelineDescriptor] = {}
_LOAD_ERRORS: list[str] = []
_ENTRY_POINTS_LOADED = False
_DEFAULT_VARIANTS = {"docling": "hybrid"}
# Pipelines the separate Python environment (VERA_PIPELINE_PYTHON) offers, the
# ones that actually run there, and the providers a host never runs in process.
_EXTERNAL_OFFERS: dict[str, _ExternalProvider] = {}
_EXTERNAL_ACTIVE: set[str] = set()
_EXTERNAL_PREFERRED: set[str] = set()


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


@dataclass(frozen=True)
class _ExternalProvider:
    """One provider offered by the separate Python environment."""

    provider: str
    python: str
    descriptors: tuple[PipelineDescriptor, ...]

    def describe(self, variant: str) -> PipelineDescriptor:
        for descriptor in self.descriptors:
            if descriptor.variant == variant:
                return descriptor
        if not variant:
            return self.descriptors[0]
        raise UnknownIngestPipelineError(
            f"Ingest pipeline {self.provider!r} in {self.python} has no variant {variant!r}."
        )

    def create(self, variant: str) -> IngestPipeline:
        spec = self.describe(variant).spec
        python = self.python

        def runs_elsewhere(source_path: str, request: IngestRequest) -> IngestResult:
            raise RuntimeError(
                f"Ingest pipeline {spec!r} runs in a separate Python environment "
                f"({python}). Convert files with vera_ingest.convert()."
            )

        return runs_elsewhere


def _normalize_provider(provider: str) -> str:
    key = provider.strip().lower()
    if not key:
        raise ValueError("ingest pipeline provider name must be non-empty")
    if ":" in key:
        raise ValueError("ingest pipeline provider name must not contain ':'")
    return key


def parse_ingest_pipeline_spec(spec: str | None) -> tuple[str, str]:
    """Resolve ``provider[:variant]`` into normalized components.

    An omitted or ``default`` variant uses the provider's registered default
    (``hybrid`` for Docling, empty for PyMuPDF), so ``pymupdf`` and
    ``pymupdf:default`` share a cache key.
    """
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
    if not separator or variant == "default":
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
        if key in _EXTERNAL_ACTIVE:
            # A local registration takes the provider back from the separate environment.
            _EXTERNAL_ACTIVE.discard(key)
            _DESCRIPTOR_FACTORIES.pop(key, None)
        for cache_key in tuple(_PIPELINE_CACHE):
            if cache_key[0] == key:
                _PIPELINE_CACHE.pop(cache_key, None)
        for cache_key in tuple(_DESCRIPTOR_CACHE):
            if cache_key[0] == key:
                _DESCRIPTOR_CACHE.pop(cache_key, None)
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
            raise ValueError(f"ingest pipeline descriptor for {provider!r} is already registered")
        _DESCRIPTOR_FACTORIES[key] = factory
        for cache_key in tuple(_DESCRIPTOR_CACHE):
            if cache_key[0] == key:
                _DESCRIPTOR_CACHE.pop(cache_key, None)
    return None


def _load_entry_point_group(group: str) -> list[Any]:
    return list(entry_points(group=group))


def _safe_load_entry_point(entry: Any, provider: str, *, kind: str) -> Any | None:
    """Load an entry point, logging a warning instead of hiding import failures."""
    try:
        return entry.load()
    except Exception as exc:  # noqa: BLE001 - one broken plugin must not hide others
        message = f"Failed to load {kind} plugin {provider!r}: {exc!r}"
        logger.warning("%s", message)
        with _REGISTRY_LOCK:
            if message not in _LOAD_ERRORS:
                _LOAD_ERRORS.append(message)
        return None


def _unknown_pipeline_message(spec: str, available: str) -> str:
    return (
        f"Unknown ingest parser pipeline {spec!r}. "
        f"Installed providers: {available}. "
        f"Install a plugin registered under the '{_ENTRY_POINT_GROUP}' "
        "entry-point group (or unpack it into a VERA_PLUGIN_DIRS folder), "
        "point VERA_PIPELINE_PYTHON at an environment that has it, "
        "or call register_ingest_pipeline()."
    )


def _collect_entry_point_factories(group: str, *, kind: str) -> list[tuple[str, Any]]:
    loaded: list[tuple[str, Any]] = []
    for entry in _load_entry_point_group(group):
        provider = entry.name.strip().lower()
        if not provider:
            continue
        factory = _safe_load_entry_point(entry, provider, kind=kind)
        if callable(factory):
            loaded.append((provider, factory))
    return loaded


def _collect_external_offers() -> dict[str, _ExternalProvider]:
    """Ask the separate Python environment, when one is set, which pipelines it has."""
    location = configured_python()
    if not location:
        return {}
    try:
        python = str(resolve_python(location))
        descriptors = list_external_descriptors(python)
    except ExternalPipelineError as exc:
        message = f"Separate Python environment {location}: {exc}"
        logger.warning("%s", message)
        with _REGISTRY_LOCK:
            if message not in _LOAD_ERRORS:
                _LOAD_ERRORS.append(message)
        return {}
    grouped: dict[str, list[PipelineDescriptor]] = {}
    for descriptor in descriptors:
        if descriptor.installed:
            grouped.setdefault(descriptor.provider, []).append(descriptor)
    return {
        provider: _ExternalProvider(provider, python, tuple(items))
        for provider, items in grouped.items()
    }


def _activate_external(provider: str) -> None:
    """Route ``provider`` to the separate environment. Caller holds the registry lock."""
    offer = _EXTERNAL_OFFERS[provider]
    _PIPELINE_FACTORIES[provider] = offer.create
    _DESCRIPTOR_FACTORIES[provider] = offer.describe
    _EXTERNAL_ACTIVE.add(provider)
    for cache in (_PIPELINE_CACHE, _DESCRIPTOR_CACHE):
        for cache_key in tuple(cache):
            if cache_key[0] == provider:
                cache.pop(cache_key, None)


def _ensure_entry_points_loaded() -> None:
    global _ENTRY_POINTS_LOADED
    with _REGISTRY_LOCK:
        if _ENTRY_POINTS_LOADED:
            return
    activate_plugin_dirs()
    pipeline_factories = _collect_entry_point_factories(_ENTRY_POINT_GROUP, kind="ingest pipeline")
    descriptor_factories = _collect_entry_point_factories(
        _DESCRIPTOR_ENTRY_POINT_GROUP, kind="ingest pipeline descriptor"
    )
    external_offers = _collect_external_offers()
    with _REGISTRY_LOCK:
        if _ENTRY_POINTS_LOADED:
            return
        for provider, factory in pipeline_factories:
            _PIPELINE_FACTORIES.setdefault(provider, factory)
        for provider, factory in descriptor_factories:
            _DESCRIPTOR_FACTORIES.setdefault(provider, factory)
        _EXTERNAL_OFFERS.update(external_offers)
        for provider in external_offers:
            # A pipeline this process has wins, unless the host never runs it here.
            if provider not in _PIPELINE_FACTORIES or provider in _EXTERNAL_PREFERRED:
                _activate_external(provider)
        _ENTRY_POINTS_LOADED = True


def prefer_external_pipelines(providers: Iterable[str]) -> None:
    """Run ``providers`` in the separate Python environment whenever it offers them.

    By default a pipeline installed in this process wins over the same
    provider in ``VERA_PIPELINE_PYTHON``. A host that never runs a provider
    in process (the desktop app and Docling) names it here. The preference
    is host configuration and survives :func:`reset_ingest_pipeline_registry`.
    """
    names = {_normalize_provider(provider) for provider in providers}
    with _REGISTRY_LOCK:
        _EXTERNAL_PREFERRED.update(names)
        if _ENTRY_POINTS_LOADED:
            for provider in names:
                if provider in _EXTERNAL_OFFERS:
                    _activate_external(provider)


def external_pipeline_python(spec: str | None) -> str | None:
    """Return the interpreter that runs ``spec``, or ``None`` when it runs in this process."""
    provider, _variant = parse_ingest_pipeline_spec(spec)
    _ensure_entry_points_loaded()
    with _REGISTRY_LOCK:
        if provider not in _EXTERNAL_ACTIVE:
            return None
        return _EXTERNAL_OFFERS[provider].python


def is_external_pipeline(spec: str | None) -> bool:
    """True when ``spec`` runs in the separate Python environment."""
    try:
        return external_pipeline_python(spec) is not None
    except UnknownIngestPipelineError:
        return False


def external_pipeline_status() -> dict[str, Any]:
    """Report the separate Python environment: its location and the pipelines it runs."""
    _ensure_entry_points_loaded()
    with _REGISTRY_LOCK:
        return {"python": configured_python(), "pipelines": sorted(_EXTERNAL_ACTIVE)}


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
            raise UnknownIngestPipelineError(_unknown_pipeline_message(spec, available))
    pipeline = factory(variant)
    if not (callable(pipeline) or callable(getattr(pipeline, "ingest", None))):
        raise TypeError(
            f"Ingest pipeline provider {provider!r} returned an object that is "
            "neither callable nor has an ingest() method."
        )
    with _REGISTRY_LOCK:
        cached = _PIPELINE_CACHE.get(cache_key)
        if cached is not None:
            return cached
        _PIPELINE_CACHE[cache_key] = pipeline
        return pipeline


def describe_ingest_pipeline(spec: str = "pymupdf") -> PipelineDescriptor:
    """Return metadata for an installed pipeline without instantiating it."""
    provider, variant = parse_ingest_pipeline_spec(spec)
    _ensure_entry_points_loaded()
    cache_key = (provider, variant)
    with _REGISTRY_LOCK:
        cached = _DESCRIPTOR_CACHE.get(cache_key)
        if cached is not None:
            return cached
        if provider not in _PIPELINE_FACTORIES:
            available = ", ".join(sorted(_PIPELINE_FACTORIES)) or "(none)"
            raise UnknownIngestPipelineError(_unknown_pipeline_message(spec, available))
        factory = _DESCRIPTOR_FACTORIES.get(provider)
    if factory is None:
        descriptor = generic_pipeline_descriptor(provider, variant)
    else:
        descriptor = factory(variant)
        if not isinstance(descriptor, PipelineDescriptor):
            raise TypeError(
                f"Ingest pipeline descriptor for {provider!r} must return PipelineDescriptor."
            )
    with _REGISTRY_LOCK:
        cached = _DESCRIPTOR_CACHE.get(cache_key)
        if cached is not None:
            return cached
        _DESCRIPTOR_CACHE[cache_key] = descriptor
        return descriptor


def list_ingest_pipelines() -> list[str]:
    """Return sorted installed provider names."""
    _ensure_entry_points_loaded()
    with _REGISTRY_LOCK:
        return sorted(_PIPELINE_FACTORIES)


def list_ingest_pipeline_descriptors(*, include_variants: bool = False) -> list[PipelineDescriptor]:
    """Return descriptors for each installed provider using its default variant.

    With ``include_variants``, each provider's default is followed by the
    other variants its descriptor advertises (``provider:variant`` specs).
    Format routing leaves this off so a variant is never picked by extension.
    """
    providers = list_ingest_pipelines()
    descriptors: list[PipelineDescriptor] = []
    for provider in providers:
        variant = _DEFAULT_VARIANTS.get(provider, "")
        spec = format_ingest_pipeline_spec(provider, variant)
        descriptor = describe_ingest_pipeline(spec)
        descriptors.append(descriptor)
        if not include_variants:
            continue
        for extra in descriptor.variants:
            if extra == descriptor.variant:
                continue
            descriptors.append(
                describe_ingest_pipeline(format_ingest_pipeline_spec(provider, extra))
            )
    return descriptors


def list_ingest_pipeline_load_errors() -> list[str]:
    """Return import/load failures collected while discovering entry points."""
    _ensure_entry_points_loaded()
    with _REGISTRY_LOCK:
        return list(_LOAD_ERRORS)


def clear_ingest_pipeline_cache() -> None:
    """Drop resolved pipeline instances and cached descriptors."""
    with _REGISTRY_LOCK:
        _PIPELINE_CACHE.clear()
        _DESCRIPTOR_CACHE.clear()


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
        _DESCRIPTOR_CACHE.clear()
        _LOAD_ERRORS.clear()
        _EXTERNAL_OFFERS.clear()
        _EXTERNAL_ACTIVE.clear()
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
