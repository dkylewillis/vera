"""Typed options and descriptor for the Markdown ingest pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from ..descriptors import (
    PipelineCapabilities,
    PipelineDescriptor,
    fields_from_dataclass,
)
from ..pipeline_options import PipelineOptions


@dataclass(frozen=True)
class MarkdownOptions(PipelineOptions):
    """Markdown-owned conversion settings.

    OCR aliases from the Convert GUI / CLI are ignored so a mixed PDF+Markdown
    convert can reuse one ``pipeline_options`` bag.
    """

    ignored_keys: ClassVar[frozenset[str]] = frozenset(
        {"ocr_mode", "ocr_language", "ocr_dpi", "ocr_download"}
    )

    chunk_size: int = field(
        default=500,
        metadata={
            "label": "Chunk size",
            "description": (
                "Target sliding-window size in whitespace-split words "
                "(not characters or LLM subword tokens)."
            ),
            "unit": "words",
            "minimum": 100,
            "maximum": 3000,
            "step": 50,
        },
    )
    overlap: int = field(
        default=75,
        metadata={
            "label": "Overlap",
            "description": (
                "Overlap between consecutive sliding-window chunks, in whitespace-split words."
            ),
            "unit": "words",
            "minimum": 0,
            "maximum": 1000,
            "step": 25,
        },
    )


def describe_pipeline(variant: str = "default") -> PipelineDescriptor:
    """Return GUI/CLI metadata without parsing a file."""
    normalized = (variant or "default").strip().lower()
    if normalized not in {"", "default"}:
        raise ValueError(f"Unknown Markdown pipeline variant {variant!r}")
    return PipelineDescriptor(
        provider="markdown",
        variant="",
        spec="markdown",
        label="markdown — headings and blocks",
        description=(
            "Markdown ingest pipeline: ATX/Setext headings, paragraphs, lists, "
            "fenced code, and GFM tables with heading-aware sliding-window chunks."
        ),
        capabilities=PipelineCapabilities(
            chunk_unit="words",
            overlap_supported=True,
            ocr_supported=False,
            ocr_engine=None,
            ocr_dpi_supported=False,
            store_original_supported=True,
            source_formats=("md", "markdown"),
        ),
        fields=fields_from_dataclass(MarkdownOptions),
        notes=(
            "Native Markdown is stored as the source attachment; citations use "
            "heading paths and text_span locators rather than PDF page boxes.",
        ),
    )
