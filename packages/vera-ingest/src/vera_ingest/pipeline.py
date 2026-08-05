from __future__ import annotations

import threading
from collections.abc import Callable
from importlib.metadata import entry_points
from typing import Protocol

from .types import IngestOptions, IngestResult

_ENTRY_POINT_GROUP = "vera.ingest_pipelines"
_REGISTRY_LOCK = threading.RLock()
_PIPELINE_FACTORIES: dict[str, Callable[[str], IngestPipeline]] = {}
_PIPELINE_CACHE: dict[tuple[str, str], IngestPipeline] = {}
_ENTRY_POINTS_LOADED = False
_DEFAULT_VARIANTS = {"docling": "hybrid"}


class IngestPipeline(Protocol):
    """Pipeline that normalizes a source document into an ingest bundle."""

    def ingest(self, source_path: str, options: IngestOptions) -> IngestResult:
        """Parse and chunk ``source_path`` without writing an archive."""
        ...


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


def register_ingest_pipeline(
    provider: str,
    factory: Callable[[str], IngestPipeline],
    *,
    replace: bool = False,
) -> None:
    """Register a provider factory called with the requested variant."""
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


def _pymupdf_factory(variant: str) -> IngestPipeline:
    from .pipelines.pymupdf import PyMuPDFPipeline

    if variant not in {"", "default"}:
        raise UnknownIngestPipelineError(
            f"Unknown PyMuPDF pipeline variant {variant!r}; use 'pymupdf'."
        )
    return PyMuPDFPipeline()


def _register_builtins() -> None:
    with _REGISTRY_LOCK:
        _PIPELINE_FACTORIES.setdefault("pymupdf", _pymupdf_factory)


def _ensure_entry_points_loaded() -> None:
    global _ENTRY_POINTS_LOADED
    with _REGISTRY_LOCK:
        if _ENTRY_POINTS_LOADED:
            return
        _register_builtins()
        try:
            selected = entry_points(group=_ENTRY_POINT_GROUP)
        except TypeError:  # pragma: no cover - Python <3.10 compatibility path
            selected = entry_points().get(_ENTRY_POINT_GROUP, [])  # type: ignore[index]
        for entry in selected:
            provider = entry.name.strip().lower()
            if not provider or provider in _PIPELINE_FACTORIES:
                continue
            try:
                factory = entry.load()
            except Exception:  # noqa: BLE001, S112 - one broken plugin must not hide others
                continue
            if callable(factory):
                _PIPELINE_FACTORIES[provider] = factory
        _ENTRY_POINTS_LOADED = True


def get_ingest_pipeline(spec: str = "pymupdf") -> IngestPipeline:
    """Resolve and cache an installed pipeline.

    Resolution is strict: an unknown provider or variant raises instead of
    falling back to the built-in PyMuPDF pipeline.
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
                f"Install a plugin registered under the '{_ENTRY_POINT_GROUP}' "
                "entry-point group, or call register_ingest_pipeline()."
            )
        pipeline = factory(variant)
        if not callable(getattr(pipeline, "ingest", None)):
            raise TypeError(
                f"Ingest pipeline provider {provider!r} returned an object without ingest()."
            )
        _PIPELINE_CACHE[cache_key] = pipeline
        return pipeline


def list_ingest_pipelines() -> list[str]:
    """Return sorted installed provider names."""
    _ensure_entry_points_loaded()
    with _REGISTRY_LOCK:
        return sorted(_PIPELINE_FACTORIES)


def clear_ingest_pipeline_cache() -> None:
    """Drop resolved pipeline instances."""
    with _REGISTRY_LOCK:
        _PIPELINE_CACHE.clear()


def reset_ingest_pipeline_registry(*, builtins: bool = True) -> None:
    """Reset registry and discovery state, primarily for tests."""
    global _ENTRY_POINTS_LOADED
    with _REGISTRY_LOCK:
        _PIPELINE_FACTORIES.clear()
        _PIPELINE_CACHE.clear()
        _ENTRY_POINTS_LOADED = False
        if builtins:
            _register_builtins()


_register_builtins()

