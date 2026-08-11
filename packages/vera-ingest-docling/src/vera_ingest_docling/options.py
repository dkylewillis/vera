"""Typed options and descriptor for the optional Docling ingest pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from vera_ingest.descriptors import (
    PipelineCapabilities,
    PipelineDescriptor,
    fields_from_dataclass,
)
from vera_ingest.pipeline_options import coerce_pipeline_options

from .languages import map_rapidocr_languages

# Legacy convert()/CLI keys that Docling intentionally ignores.
_IGNORED_COMPAT_KEYS = {"overlap", "ocr_dpi"}


@dataclass(frozen=True)
class DoclingOptions:
    """Docling/RapidOCR-owned conversion settings.

    Each field's ``metadata`` doubles as its CLI/GUI descriptor entry (see
    :func:`vera_ingest.descriptors.fields_from_dataclass`), so a setting's
    key, default, and presentation live in one place. ``from_mapping`` uses
    :func:`vera_ingest.pipeline_options.coerce_pipeline_options` for the
    mechanical bool/int/choice/string validation, then does the one thing
    that helper can't: remapping ``ocr_language`` from Tesseract-style codes
    to RapidOCR's. This class does *not* inherit
    :class:`~vera_ingest.pipeline_options.PipelineOptions` for that reason —
    see that module's docstring for when to inherit it versus call the
    helper function directly.
    """

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
                "RapidOCR language code (en). Common Tesseract aliases such as "
                "eng are accepted and mapped."
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

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None = None) -> DoclingOptions:
        coerced = coerce_pipeline_options(
            cls, raw, label="Docling", ignored=_IGNORED_COMPAT_KEYS
        )
        # Normalize at parse time so Tesseract ``eng`` never reaches RapidOCR;
        # coerce_pipeline_options() only validates ocr_language is a string,
        # it doesn't know about this pipeline-specific remapping.
        coerced["ocr_language"] = ",".join(map_rapidocr_languages(coerced["ocr_language"]))
        return cls(**coerced)


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
            "First conversion may download Docling model artifacts; set DOCLING_ARTIFACTS_PATH for offline caches.",
            "On memory errors (bad_alloc), VERA retries failed pages then falls back to pypdfium2 automatically.",
            "Install with: uv sync --extra docling",
        ),
    )
