"""Typed options and descriptor for the OOXML ingest pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from vera_ingest.descriptors import (
    PipelineCapabilities,
    PipelineDescriptor,
    fields_from_dataclass,
)
from vera_ingest.pipeline_options import PipelineOptions

OOXML_SOURCE_FORMATS: tuple[str, ...] = ("docx", "pptx", "xlsx")


@dataclass(frozen=True)
class OoxmlOptions(PipelineOptions):
    """Settings owned by the lightweight Office pipeline.

    OCR aliases from a mixed-folder convert are ignored. Word and PowerPoint
    use ``chunk_size`` and ``overlap``. Excel keeps each row group intact and
    uses ``rows_per_chunk`` instead of splitting a table on word count.
    """

    ignored_keys: ClassVar[frozenset[str]] = frozenset(
        {"ocr_mode", "ocr_language", "ocr_dpi", "ocr_download"}
    )

    chunk_size: int = field(
        default=500,
        metadata={
            "label": "Chunk size",
            "description": (
                "Target sliding-window size in whitespace-split words for Word "
                "and PowerPoint (not characters or LLM subword tokens)."
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
                "Overlap between consecutive Word and PowerPoint chunks, "
                "in whitespace-split words."
            ),
            "unit": "words",
            "minimum": 0,
            "maximum": 1000,
            "step": 25,
        },
    )
    rows_per_chunk: int = field(
        default=40,
        metadata={
            "label": "Rows per chunk",
            "description": (
                "Excel data rows kept together in one chunk. The header row is "
                "repeated in every chunk and the table is not split mid-row."
            ),
            "unit": "rows",
            "minimum": 1,
            "maximum": 500,
            "step": 1,
        },
    )
    include_notes: bool = field(
        default=True,
        metadata={
            "label": "Include speaker notes",
            "description": "Index PowerPoint speaker notes with the slide they belong to.",
        },
    )


def describe_pipeline(variant: str = "default") -> PipelineDescriptor:
    """Return GUI/CLI metadata without parsing a file."""
    normalized = (variant or "default").strip().lower()
    if normalized not in {"", "default"}:
        raise ValueError(f"Unknown OOXML pipeline variant {variant!r}")
    return PipelineDescriptor(
        provider="ooxml",
        variant="",
        spec="ooxml",
        label="ooxml — Word, PowerPoint, and Excel",
        description=(
            "Lightweight Office ingest: Word headings and tables, PowerPoint "
            "slides and notes, and Excel sheets as row-group tables."
        ),
        capabilities=PipelineCapabilities(
            chunk_unit="words",
            overlap_supported=True,
            ocr_supported=False,
            ocr_engine=None,
            ocr_dpi_supported=False,
            store_original_supported=True,
            source_formats=OOXML_SOURCE_FORMATS,
        ),
        fields=fields_from_dataclass(OoxmlOptions),
        notes=(
            "The original Office file is stored for export. Word highlights a "
            "Markdown preview. Slides and sheets use slide and sheet_range locators.",
        ),
    )
