"""Optional Docling HybridChunker ingest pipeline for VERA."""

from __future__ import annotations

from vera_ingest.pipeline import UnknownIngestPipelineError

from .pipeline import DoclingHybridPipeline

__all__ = [
    "DoclingHybridPipeline",
    "create_pipeline",
]


def create_pipeline(variant: str = "hybrid") -> DoclingHybridPipeline:
    """Entry-point factory for ``vera.ingest_pipelines`` provider ``docling``."""
    normalized = (variant or "hybrid").strip().lower()
    if normalized not in {"", "hybrid"}:
        raise UnknownIngestPipelineError(
            f"Unknown Docling pipeline variant {variant!r}; use 'docling' or 'docling:hybrid'."
        )
    return DoclingHybridPipeline()
