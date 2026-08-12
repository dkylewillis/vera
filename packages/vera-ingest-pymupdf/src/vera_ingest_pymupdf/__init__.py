"""Default PyMuPDF ingest pipeline for VERA."""

from __future__ import annotations

from vera_ingest.descriptors import PipelineDescriptor
from vera_ingest.pipeline import IngestPipeline, UnknownIngestPipelineError
from vera_ingest.types import ParsedBlock, ParsedPage

from .options import PyMuPDFOptions, describe_pipeline
from .parser import parse_pdf, parse_pdf_structured
from .pipeline import pymupdf_pipeline
from .tessdata_manager import (
    OCRLanguageDownloadError,
    UnknownOCRLanguageError,
    default_ocr_language_cache_dir,
    describe_ocr_languages,
    download_ocr_language_data,
)

__all__ = [
    "OCRLanguageDownloadError",
    "ParsedBlock",
    "ParsedPage",
    "PyMuPDFOptions",
    "UnknownOCRLanguageError",
    "create_descriptor",
    "create_pipeline",
    "default_ocr_language_cache_dir",
    "describe_ocr_languages",
    "describe_pipeline",
    "download_ocr_language_data",
    "parse_pdf",
    "parse_pdf_structured",
    "pymupdf_pipeline",
]


def create_pipeline(variant: str = "default") -> IngestPipeline:
    """Entry-point factory for ``vera.ingest_pipelines`` provider ``pymupdf``."""
    normalized = (variant or "default").strip().lower()
    if normalized not in {"", "default"}:
        raise UnknownIngestPipelineError(
            f"Unknown PyMuPDF pipeline variant {variant!r}; use 'pymupdf'."
        )
    return pymupdf_pipeline


def create_descriptor(variant: str = "default") -> PipelineDescriptor:
    """Entry-point factory for ``vera.ingest_pipeline_descriptors``."""
    try:
        return describe_pipeline(variant)
    except ValueError as exc:
        raise UnknownIngestPipelineError(str(exc)) from exc
