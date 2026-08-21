"""Optional Docling HybridChunker ingest pipeline for VERA."""

from __future__ import annotations

from typing import Any

from vera_ingest.descriptors import PipelineDescriptor
from vera_ingest.pipeline import (
    IngestPipeline,
    UnknownIngestPipelineError,
    register_ingest_pipeline,
    register_ingest_pipeline_descriptor,
)

from .options import DoclingOptions, _docling_runtime_available, describe_pipeline

__all__ = [
    "DoclingHybridPipeline",
    "DoclingOptions",
    "create_descriptor",
    "create_pipeline",
    "describe_pipeline",
    "ensure_registered",
]


def __getattr__(name: str) -> Any:
    if name == "DoclingHybridPipeline":
        from .pipeline import DoclingHybridPipeline

        return DoclingHybridPipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def create_pipeline(variant: str = "hybrid") -> IngestPipeline:
    """Entry-point factory for ``vera.ingest_pipelines`` provider ``docling``."""
    normalized = (variant or "hybrid").strip().lower()
    if normalized not in {"", "hybrid"}:
        raise UnknownIngestPipelineError(
            f"Unknown Docling pipeline variant {variant!r}; use 'docling' or 'docling:hybrid'."
        )
    if not _docling_runtime_available():
        raise UnknownIngestPipelineError(
            "Docling is not installed in this environment. "
            "Install with: python -m pip install 'vera-ingest-docling>=0.3.0'"
        )
    from vera_ingest.timing import timed_step

    with timed_step("import_docling_pipeline"):
        from .pipeline import DoclingHybridPipeline

    return DoclingHybridPipeline()


def create_descriptor(variant: str = "hybrid") -> PipelineDescriptor:
    """Entry-point factory for ``vera.ingest_pipeline_descriptors``."""
    try:
        return describe_pipeline(variant)
    except ValueError as exc:
        raise UnknownIngestPipelineError(str(exc)) from exc


def ensure_registered(*, replace: bool = True) -> None:
    """Register the ``docling`` pipeline without relying on package metadata.

    Entry-point discovery fails in PyInstaller freezes and PYTHONPATH-only
    source runs that never install ``vera-ingest-docling`` dist-info.
    """
    register_ingest_pipeline("docling", create_pipeline, replace=replace)
    register_ingest_pipeline_descriptor("docling", create_descriptor, replace=replace)


ensure_registered()
