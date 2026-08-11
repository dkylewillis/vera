"""Typed options and descriptor for the PyMuPDF ingest pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from vera_ingest.descriptors import (
    PipelineCapabilities,
    PipelineDescriptor,
    PipelineField,
    PipelineFieldChoice,
)
from vera_ingest.option_parsing import (
    reject_unknown_keys,
    require_bool,
    require_choice,
    require_mapping,
    require_non_negative_int,
    require_positive_int,
    require_string,
)

from .tessdata_manager import language_choice_labels

_ALLOWED_KEYS = {
    "chunk_size",
    "overlap",
    "ocr_mode",
    "ocr_language",
    "ocr_dpi",
    "ocr_download",
}
_OCR_MODES = {"auto", "off", "force"}


def _ocr_language_choices() -> tuple[PipelineFieldChoice, ...]:
    """Bundled + curated downloadable Tesseract codes for the Convert GUI."""
    return tuple(
        PipelineFieldChoice(code, label) for code, label in language_choice_labels()
    )


@dataclass(frozen=True)
class PyMuPDFOptions:
    """PyMuPDF/Tesseract-owned conversion settings."""

    chunk_size: int = 500
    overlap: int = 75
    ocr_mode: str = "auto"
    ocr_language: str = "eng"
    ocr_dpi: int = 300
    ocr_download: bool = False

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None = None) -> PyMuPDFOptions:
        data = reject_unknown_keys(
            require_mapping(raw, label="PyMuPDF pipeline_options"),
            allowed=_ALLOWED_KEYS,
            label="PyMuPDF",
        )
        chunk_size = require_positive_int(
            data.get("chunk_size", 500),
            name="chunk_size",
        )
        overlap = require_non_negative_int(
            data.get("overlap", 75),
            name="overlap",
        )
        ocr_mode = require_choice(
            data.get("ocr_mode", "auto"),
            name="ocr_mode",
            choices=_OCR_MODES,
        )
        ocr_language = require_string(
            data.get("ocr_language", "eng"),
            name="ocr_language",
        )
        ocr_dpi = require_positive_int(
            data.get("ocr_dpi", 300),
            name="ocr_dpi",
        )
        ocr_download = require_bool(
            data.get("ocr_download", False),
            name="ocr_download",
        )
        return cls(
            chunk_size=chunk_size,
            overlap=overlap,
            ocr_mode=ocr_mode,
            ocr_language=ocr_language,
            ocr_dpi=ocr_dpi,
            ocr_download=ocr_download,
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
        fields=(
            PipelineField(
                key="chunk_size",
                label="Chunk size",
                type="integer",
                default=500,
                description="Target chunk size in words/characters for sliding windows.",
                unit="characters",
                minimum=100,
                maximum=3000,
                step=50,
            ),
            PipelineField(
                key="overlap",
                label="Overlap",
                type="integer",
                default=75,
                description="Overlap between consecutive sliding-window chunks.",
                unit="characters",
                minimum=0,
                maximum=1000,
                step=25,
            ),
            PipelineField(
                key="ocr_mode",
                label="OCR mode",
                type="enum",
                default="auto",
                description="When to OCR image-dominant pages.",
                choices=(
                    PipelineFieldChoice("auto", "Auto"),
                    PipelineFieldChoice("off", "Off"),
                    PipelineFieldChoice("force", "Force"),
                ),
            ),
            PipelineField(
                key="ocr_language",
                label="OCR language",
                type="enum",
                default="eng",
                description=(
                    "Tesseract language code from VERA's bundled/downloadable "
                    "registry (for example spa). Choose Custom for combinations "
                    "such as eng+spa or a manually installed TESSDATA_PREFIX code."
                ),
                choices=_ocr_language_choices(),
                allow_custom=True,
                placeholder="eng",
            ),
            PipelineField(
                key="ocr_dpi",
                label="OCR DPI",
                type="integer",
                default=300,
                description="Rasterization DPI used for Tesseract OCR.",
                unit="dpi",
                minimum=72,
                maximum=600,
                step=10,
            ),
            PipelineField(
                key="ocr_download",
                label="Allow OCR language download",
                type="boolean",
                default=False,
                description=(
                    "Fetch missing Tesseract language data for 'OCR language' "
                    "automatically from a curated, checksum-verified registry "
                    "and cache it locally. English is always bundled; other "
                    "languages otherwise require a manual TESSDATA_PREFIX install."
                ),
            ),
        ),
    )
