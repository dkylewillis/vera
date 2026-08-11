"""Typed options and descriptor for the PyMuPDF ingest pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from vera_ingest.descriptors import (
    PipelineCapabilities,
    PipelineDescriptor,
    fields_from_dataclass,
)
from vera_ingest.option_parsing import (
    allowed_keys_from_dataclass,
    reject_unknown_keys,
    require_bool,
    require_choice,
    require_mapping,
    require_non_negative_int,
    require_positive_int,
    require_string,
)

from .tessdata_manager import language_choice_labels

_OCR_MODES = {"auto", "off", "force"}


def _ocr_language_choices() -> tuple[tuple[str, str], ...]:
    """Bundled + curated downloadable Tesseract codes for the Convert GUI."""
    return tuple(language_choice_labels())


@dataclass(frozen=True)
class PyMuPDFOptions:
    """PyMuPDF/Tesseract-owned conversion settings.

    Each field's ``metadata`` doubles as its CLI/GUI descriptor entry (see
    :func:`vera_ingest.descriptors.fields_from_dataclass`), so a setting's
    key, default, and presentation live in one place instead of being kept in
    sync by hand across a dataclass field, ``from_mapping``, and a separate
    descriptor field list.
    """

    chunk_size: int = field(
        default=500,
        metadata={
            "label": "Chunk size",
            "description": "Target chunk size in words/characters for sliding windows.",
            "unit": "characters",
            "minimum": 100,
            "maximum": 3000,
            "step": 50,
        },
    )
    overlap: int = field(
        default=75,
        metadata={
            "label": "Overlap",
            "description": "Overlap between consecutive sliding-window chunks.",
            "unit": "characters",
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

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None = None) -> PyMuPDFOptions:
        data = reject_unknown_keys(
            require_mapping(raw, label="PyMuPDF pipeline_options"),
            allowed=allowed_keys_from_dataclass(cls),
            label="PyMuPDF",
        )
        return cls(
            chunk_size=require_positive_int(
                data.get("chunk_size", cls.chunk_size), name="chunk_size"
            ),
            overlap=require_non_negative_int(
                data.get("overlap", cls.overlap), name="overlap"
            ),
            ocr_mode=require_choice(
                data.get("ocr_mode", cls.ocr_mode), name="ocr_mode", choices=_OCR_MODES
            ),
            ocr_language=require_string(
                data.get("ocr_language", cls.ocr_language), name="ocr_language"
            ),
            ocr_dpi=require_positive_int(
                data.get("ocr_dpi", cls.ocr_dpi), name="ocr_dpi"
            ),
            ocr_download=require_bool(
                data.get("ocr_download", cls.ocr_download), name="ocr_download"
            ),
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
            chunk_unit="characters",
            overlap_supported=True,
            ocr_supported=True,
            ocr_engine="tesseract",
            ocr_dpi_supported=True,
        ),
        fields=fields_from_dataclass(PyMuPDFOptions),
    )
