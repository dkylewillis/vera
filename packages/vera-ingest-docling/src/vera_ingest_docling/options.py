"""Typed options and descriptor for the optional Docling ingest pipeline."""

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
    require_choice,
    require_mapping,
    require_positive_int,
    require_string,
)

# Legacy convert()/CLI keys that Docling intentionally ignores.
_IGNORED_COMPAT_KEYS = {"overlap", "ocr_dpi"}
_ALLOWED_KEYS = {"chunk_size", "ocr_mode", "ocr_language"}
_OCR_MODES = {"auto", "off", "force"}


@dataclass(frozen=True)
class DoclingOptions:
    """Docling/RapidOCR-owned conversion settings."""

    chunk_size: int = 500
    ocr_mode: str = "auto"
    ocr_language: str = "en"

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None = None) -> DoclingOptions:
        data = reject_unknown_keys(
            require_mapping(raw, label="Docling pipeline_options"),
            allowed=_ALLOWED_KEYS,
            ignored=_IGNORED_COMPAT_KEYS,
            label="Docling",
        )
        chunk_size = require_positive_int(
            data.get("chunk_size", 500),
            name="chunk_size",
        )
        ocr_mode = require_choice(
            data.get("ocr_mode", "auto"),
            name="ocr_mode",
            choices=_OCR_MODES,
        )
        ocr_language = require_string(
            data.get("ocr_language", "en"),
            name="ocr_language",
        )
        return cls(
            chunk_size=chunk_size,
            ocr_mode=ocr_mode,
            ocr_language=ocr_language,
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
        fields=(
            PipelineField(
                key="chunk_size",
                label="Chunk size",
                type="integer",
                default=500,
                description="HybridChunker token limit (whitespace tokens in VERA).",
                unit="tokens",
                minimum=100,
                maximum=3000,
                step=50,
            ),
            PipelineField(
                key="ocr_mode",
                label="OCR mode",
                type="enum",
                default="auto",
                description="RapidOCR mode mapped through Docling.",
                choices=(
                    PipelineFieldChoice("auto", "Auto"),
                    PipelineFieldChoice("off", "Off"),
                    PipelineFieldChoice("force", "Force"),
                ),
            ),
            PipelineField(
                key="ocr_language",
                label="OCR language",
                type="string",
                default="en",
                description=(
                    "RapidOCR language code (en). Common Tesseract aliases such as "
                    "eng are accepted and mapped."
                ),
                placeholder="en",
            ),
        ),
        notes=(
            "Overlap is not applied by Docling HybridChunker.",
            "First conversion may download Docling model artifacts; set DOCLING_ARTIFACTS_PATH for offline caches.",
            "Install with: uv sync --extra docling",
        ),
    )
