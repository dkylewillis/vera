"""Typed options and descriptor for the optional Docling ingest pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from vera_ingest.descriptors import (
    PipelineCapabilities,
    PipelineDescriptor,
    fields_from_dataclass,
)
from vera_ingest.pipeline_options import PipelineOptions


@dataclass(frozen=True)
class DoclingOptions(PipelineOptions):
    """Docling/RapidOCR-owned conversion settings.

    Each field's ``metadata`` doubles as its CLI/GUI descriptor entry (see
    :func:`vera_ingest.descriptors.fields_from_dataclass`) and drives its own
    validation (inherited from :class:`~vera_ingest.pipeline_options.PipelineOptions`),
    so a setting's key, default, presentation, and validation all live in one
    place. ``ocr_language`` expects a RapidOCR-native code (for example
    ``en``) — Docling does not translate Tesseract-style codes such as
    ``eng``, so this pipeline's OCR language is a genuinely different setting
    from PyMuPDF's, not a shared vocabulary.
    """

    # `overlap`/`ocr_dpi` are PyMuPDF-only legacy convert()/CLI aliases that
    # don't apply here; silently drop them instead of rejecting as unknown.
    ignored_keys: ClassVar[frozenset[str]] = frozenset({"overlap", "ocr_dpi"})

    chunk_size: int = field(
        default=500,
        metadata={
            "label": "Chunk size",
            "description": "HybridChunker token limit (whitespace tokens in VERA).",
            "unit": "tokens",
            "minimum": 100,
            "maximum": 3000,
            "step": 50,
        },
    )
    ocr_mode: str = field(
        default="auto",
        metadata={
            "label": "OCR mode",
            "type": "enum",
            "description": "RapidOCR mode mapped through Docling.",
            "choices": (("auto", "Auto"), ("off", "Off"), ("force", "Force")),
        },
    )
    ocr_language: str = field(
        default="en",
        metadata={
            "label": "OCR language",
            "description": (
                "RapidOCR-native language code (for example en, fr, cyrillic). "
                "Combine multiple with + or , (for example en+fr). Not "
                "Tesseract-compatible: PyMuPDF's 'eng' is not a valid value here."
            ),
            "placeholder": "en",
        },
    )
    pdf_backend: str = field(
        default="docling_parse",
        metadata={
            "label": "PDF backend",
            "type": "enum",
            "description": (
                "PDF parsing backend. docling_parse gives the best table/layout "
                "quality; pypdfium2 uses less memory and is more stable on large "
                "or complex PDFs (may reduce table fidelity)."
            ),
            "choices": (
                ("docling_parse", "docling-parse (default)"),
                ("pypdfium2", "pypdfium2 (low memory)"),
            ),
        },
    )


def describe_pipeline(variant: str = "hybrid") -> PipelineDescriptor:
    """Return GUI/CLI metadata without loading Docling or Torch."""
    normalized = (variant or "hybrid").strip().lower()
    if normalized not in {"", "hybrid"}:
        raise ValueError(
            f"Unknown Docling pipeline variant {variant!r}; use 'docling' or 'docling:hybrid'."
        )
    return PipelineDescriptor(
        provider="docling",
        variant="hybrid",
        spec="docling",
        label="docling — HybridChunker",
        description=(
            "Optional Docling DocumentConverter + HybridChunker ingest pipeline "
            "with RapidOCR support."
        ),
        capabilities=PipelineCapabilities(
            chunk_unit="tokens",
            overlap_supported=False,
            ocr_supported=True,
            ocr_engine="rapidocr",
            ocr_dpi_supported=False,
        ),
        fields=fields_from_dataclass(DoclingOptions),
        notes=(
            "Overlap is not applied by Docling HybridChunker.",
            "OCR language uses RapidOCR-native codes, not Tesseract's — 'en', not 'eng'.",
            "First conversion may download Docling model artifacts; set DOCLING_ARTIFACTS_PATH for offline caches.",
            "On memory errors (bad_alloc), VERA retries failed pages then falls back to pypdfium2 automatically.",
            "Install with: uv sync --extra docling",
        ),
    )
