"""Typed options and descriptor for the optional Docling ingest pipeline."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib.util import find_spec
from pathlib import Path
from typing import Any, ClassVar

from vera_ingest.descriptors import (
    PipelineCapabilities,
    PipelineDescriptor,
    fields_from_dataclass,
)
from vera_ingest.pipeline_options import PipelineOptions

# Suffixes advertised on the descriptor and accepted by convert discovery.
# Visual grounding and PDF page recovery remain PDF-only.
DOCLING_SOURCE_FORMATS: tuple[str, ...] = (
    "pdf",
    "docx",
    "pptx",
    "xlsx",
    "html",
    "htm",
)


@dataclass(frozen=True)
class DoclingOptions(PipelineOptions):
    """Docling/RapidOCR-owned conversion settings.

    Each field's ``metadata`` doubles as its CLI/GUI descriptor entry (see
    :func:`vera_ingest.descriptors.fields_from_dataclass`) and drives its own
    validation (inherited from :class:`~vera_ingest.pipeline_options.PipelineOptions`),
    so a setting's key, default, presentation, and validation all live in one
    place. ``ocr_language`` expects a RapidOCR-native code (for example
    ``en``). The Tesseract default ``eng`` (and ``eng+…``) is remapped to
    RapidOCR ``en`` so a legacy :class:`~vera_ingest.types.IngestOptions`
    call does not leak a Tesseract code; other codes pass through as given.
    """

    # `overlap`/`ocr_dpi` are PyMuPDF-only legacy convert()/CLI aliases that
    # don't apply here; silently drop them instead of rejecting as unknown.
    ignored_keys: ClassVar[frozenset[str]] = frozenset({"overlap", "ocr_dpi"})

    chunk_size: int = field(
        default=500,
        metadata={
            "label": "Chunk size",
            "description": (
                "HybridChunker limit in whitespace-split words (not LLM subword tokens)."
            ),
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
                "Combine multiple with + or , (for example en+fr). The Tesseract "
                "default 'eng' is remapped to 'en'."
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
        data = dict(raw) if raw else {}
        if "ocr_language" in data:
            data["ocr_language"] = _remap_tesseract_default_ocr_language(data["ocr_language"])
        return super().from_mapping(data)


def _remap_tesseract_default_ocr_language(value: Any) -> Any:
    """Map Tesseract default ``eng`` tokens to RapidOCR ``en``."""
    if not isinstance(value, str):
        return value
    parts = [part.strip() for part in value.replace("+", ",").split(",")]
    remapped: list[str] = []
    for part in parts:
        if not part:
            continue
        remapped.append("en" if part.lower() == "eng" else part)
    return "+".join(remapped) if remapped else "en"


def _docling_runtime_available() -> bool:
    """True when the Docling packages needed for conversion are importable."""
    return find_spec("docling") is not None and find_spec("docling_core") is not None


def source_format_from_path(path: str | Path) -> str:
    """Return the advertised Docling suffix for ``path``.

    Raises:
        ValueError: If the extension is not in :data:`DOCLING_SOURCE_FORMATS`.
    """
    suffix = Path(path).suffix.lower().lstrip(".")
    if suffix in DOCLING_SOURCE_FORMATS:
        return suffix
    supported = ", ".join(f".{item}" for item in DOCLING_SOURCE_FORMATS)
    label = Path(path).suffix or "extensionless"
    raise ValueError(f"Docling ingest does not support {label} files (supports: {supported}).")


def is_pdf_source(path: str | Path) -> bool:
    """True when ``path`` is a PDF (page recovery applies)."""
    return Path(path).suffix.lower().lstrip(".") == "pdf"


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
        label="Advanced layout (slower)",
        description=(
            "Docling DocumentConverter + HybridChunker. PDFs use RapidOCR and layout "
            "models (slower than PyMuPDF; better tables, layout, and scans). DOCX, "
            "PPTX, XLSX, and HTML are search-only (no page recovery or highlight "
            "overlay). First PDF conversion may download layout models into "
            "DOCLING_ARTIFACTS_PATH."
        ),
        installed=_docling_runtime_available(),
        capabilities=PipelineCapabilities(
            chunk_unit="tokens",
            overlap_supported=False,
            ocr_supported=True,
            ocr_engine="rapidocr",
            ocr_dpi_supported=False,
            source_formats=DOCLING_SOURCE_FORMATS,
        ),
        fields=fields_from_dataclass(DoclingOptions),
        notes=(
            "Overlap is not applied by Docling HybridChunker.",
            "OCR language uses RapidOCR-native codes, not Tesseract's — 'en', not 'eng'.",
            "OCR, pdf_backend, and layout-model download apply to PDFs only.",
            "DOCX, PPTX, XLSX, and HTML are searchable; citations may lack page boxes.",
            "On PDF memory errors (bad_alloc), VERA retries failed pages, then whole-document pypdfium2, then page-batch pypdfium2.",
            'CLI install: pip install "vera-cli[docling]>=0.3.0" or uv sync --extra docling',
        ),
    )
