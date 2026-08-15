"""Optional Docling HybridChunker ingest pipeline for VERA."""

from __future__ import annotations

from typing import Any

from vera_ingest.descriptors import PipelineDescriptor
from vera_ingest.pipeline import IngestPipeline, UnknownIngestPipelineError

from .options import DoclingOptions, _docling_runtime_available, describe_pipeline

__all__ = [
    "DoclingHybridPipeline",
    "DoclingOptions",
    "create_pipeline",
    "describe_pipeline",
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
    from .pipeline import DoclingHybridPipeline

    return DoclingHybridPipeline()


def create_descriptor(variant: str = "hybrid") -> PipelineDescriptor:
    """Entry-point factory for ``vera.ingest_pipeline_descriptors``."""
    try:
        return describe_pipeline(variant)
    except ValueError as exc:
        raise UnknownIngestPipelineError(str(exc)) from exc
