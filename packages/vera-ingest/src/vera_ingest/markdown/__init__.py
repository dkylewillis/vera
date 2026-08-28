"""First-party Markdown ingest pipeline for VERA."""

from __future__ import annotations

from ..descriptors import PipelineDescriptor
from ..pipeline import (
    IngestPipeline,
    UnknownIngestPipelineError,
    register_ingest_pipeline,
    register_ingest_pipeline_descriptor,
)
from .options import MarkdownOptions, describe_pipeline
from .parser import MarkdownBlock, parse_markdown
from .pipeline import markdown_pipeline

__all__ = [
    "MarkdownBlock",
    "MarkdownOptions",
    "create_descriptor",
    "create_pipeline",
    "describe_pipeline",
    "ensure_registered",
    "markdown_pipeline",
    "parse_markdown",
]


def create_pipeline(variant: str = "default") -> IngestPipeline:
    """Entry-point factory for ``vera.ingest_pipelines`` provider ``markdown``."""
    normalized = (variant or "default").strip().lower()
    if normalized not in {"", "default"}:
        raise UnknownIngestPipelineError(
            f"Unknown Markdown pipeline variant {variant!r}; use 'markdown'."
        )
    return markdown_pipeline


def create_descriptor(variant: str = "default") -> PipelineDescriptor:
    """Entry-point factory for ``vera.ingest_pipeline_descriptors``."""
    try:
        return describe_pipeline(variant)
    except ValueError as exc:
        raise UnknownIngestPipelineError(str(exc)) from exc


def ensure_registered(*, replace: bool = True) -> None:
    """Register the ``markdown`` pipeline without relying on package metadata."""
    register_ingest_pipeline("markdown", create_pipeline, replace=replace)
    register_ingest_pipeline_descriptor("markdown", create_descriptor, replace=replace)


ensure_registered()
