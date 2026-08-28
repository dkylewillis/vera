"""Typed options and descriptor for the PyMuPDF ingest pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field

from vera_ingest.descriptors import (
    PipelineCapabilities,
    PipelineDescriptor,
    fields_from_dataclass,
)
from vera_ingest.pipeline_options import PipelineOptions

from .tessdata_manager import language_choice_labels


def _ocr_language_choices() -> tuple[tuple[str, str], ...]:
    """Bundled + curated downloadable Tesseract codes for the Convert GUI."""
    return tuple(language_choice_labels())


@dataclass(frozen=True)
class PyMuPDFOptions(PipelineOptions):
    """PyMuPDF/Tesseract-owned conversion settings.

    Each field's ``metadata`` doubles as its CLI/GUI descriptor entry (see
    :func:`vera_ingest.descriptors.fields_from_dataclass`) and drives its own
    validation (see :class:`vera_ingest.pipeline_options.PipelineOptions`),
    so a setting's key, default, presentation, and validation all live in one
    place — ``from_mapping`` itself is inherited from
    :class:`~vera_ingest.pipeline_options.PipelineOptions`, not written here.
    """

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
    ocr_mode: str = field(
        default="auto",
        metadata={
            "label": "OCR mode",
            "type": "enum",
            "description": "When to OCR image-dominant pages.",
            "choices": (("auto", "Auto"), ("off", "Off"), ("force", "Force")),
        },
    )
    ocr_language: str = field(
        default="eng",
        metadata={
            "label": "OCR language",
            "type": "enum",
            "description": (
                "Tesseract language code from VERA's bundled/downloadable "
                "registry (for example spa). Choose Custom for combinations "
                "such as eng+spa or a manually installed TESSDATA_PREFIX code."
            ),
            "choices": _ocr_language_choices(),
            "allow_custom": True,
            "placeholder": "eng",
        },
    )
    ocr_dpi: int = field(
        default=300,
        metadata={
            "label": "OCR DPI",
            "description": "Rasterization DPI used for Tesseract OCR.",
            "unit": "dpi",
            "minimum": 72,
            "maximum": 600,
            "step": 10,
        },
    )
    ocr_download: bool = field(
        default=False,
        metadata={
            "label": "Allow OCR language download",
            "description": (
                "Fetch missing Tesseract language data for 'OCR language' "
                "automatically from a curated, checksum-verified registry "
                "and cache it locally. English is always bundled; other "
                "languages otherwise require a manual TESSDATA_PREFIX install."
            ),
        },
    )


def describe_pipeline(variant: str = "default") -> PipelineDescriptor:
    """Return GUI/CLI metadata without loading PyMuPDF models."""
    normalized = (variant or "default").strip().lower()
    if normalized not in {"", "default"}:
        raise ValueError(f"Unknown PyMuPDF pipeline variant {variant!r}")
    return PipelineDescriptor(
        provider="pymupdf",
        variant="",
        spec="pymupdf",
        label="pymupdf — default PDF pipeline",
        description=(
            "PDF ingest pipeline using PyMuPDF parsing and optional "
            "Tesseract OCR with sliding-window chunking."
        ),
        capabilities=PipelineCapabilities(
            chunk_unit="words",
            overlap_supported=True,
            ocr_supported=True,
            ocr_engine="tesseract",
            ocr_dpi_supported=True,
            source_formats=("pdf",),
        ),
        fields=fields_from_dataclass(PyMuPDFOptions),
    )
