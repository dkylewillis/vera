"""Optional Docling HybridChunker ingest pipeline for VERA."""

from __future__ import annotations

from vera_ingest.descriptors import PipelineDescriptor
from vera_ingest.pipeline import UnknownIngestPipelineError

from .options import DoclingOptions, describe_pipeline
from .pipeline import DoclingHybridPipeline

__all__ = [
    "DoclingHybridPipeline",
    "DoclingOptions",
    "create_pipeline",
    "describe_pipeline",
]


def create_pipeline(variant: str = "hybrid") -> DoclingHybridPipeline:
    """Entry-point factory for ``vera.ingest_pipelines`` provider ``docling``."""
    normalized = (variant or "hybrid").strip().lower()
    if normalized not in {"", "hybrid"}:
        raise UnknownIngestPipelineError(
            f"Unknown Docling pipeline variant {variant!r}; use 'docling' or 'docling:hybrid'."
        )
    return DoclingHybridPipeline()


def create_descriptor(variant: str = "hybrid") -> PipelineDescriptor:
    """Entry-point factory for ``vera.ingest_pipeline_descriptors``."""
    try:
        return describe_pipeline(variant)
    except ValueError as exc:
        raise UnknownIngestPipelineError(str(exc)) from exc
