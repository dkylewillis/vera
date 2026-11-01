"""Lightweight Word, PowerPoint, and Excel ingest pipeline for VERA."""

from __future__ import annotations

from vera_ingest.descriptors import PipelineDescriptor
from vera_ingest.pipeline import (
    IngestPipeline,
    UnknownIngestPipelineError,
    register_ingest_pipeline,
    register_ingest_pipeline_descriptor,
)

from .options import OoxmlOptions, describe_pipeline
from .pipeline import ooxml_pipeline

__all__ = [
    "OoxmlOptions",
    "create_descriptor",
    "create_pipeline",
    "describe_pipeline",
    "ensure_registered",
    "ooxml_pipeline",
]


def create_pipeline(variant: str = "default") -> IngestPipeline:
    """Entry-point factory for ``vera.ingest_pipelines`` provider ``ooxml``."""
    normalized = (variant or "default").strip().lower()
    if normalized not in {"", "default"}:
        raise UnknownIngestPipelineError(
            f"Unknown OOXML pipeline variant {variant!r}; use 'ooxml'."
        )
    return ooxml_pipeline


def create_descriptor(variant: str = "default") -> PipelineDescriptor:
    """Entry-point factory for ``vera.ingest_pipeline_descriptors``."""
    try:
        return describe_pipeline(variant)
    except ValueError as exc:
        raise UnknownIngestPipelineError(str(exc)) from exc


def ensure_registered(*, replace: bool = True) -> None:
    """Register the ``ooxml`` pipeline without relying on package metadata."""
    register_ingest_pipeline("ooxml", create_pipeline, replace=replace)
    register_ingest_pipeline_descriptor("ooxml", create_descriptor, replace=replace)


ensure_registered()
