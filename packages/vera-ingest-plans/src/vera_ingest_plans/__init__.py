"""``plans``: a VERA ingest pipeline plugin for construction drawing sets.

It runs the PyMuPDF parser with drawn-lettering OCR turned on, and keeps
heading text (detail titles) in the chunk body so a title is searchable.
The desktop app does not bundle it; install the wheel from
**Settings > Plugins** or ``pip install`` it beside the CLI.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from vera_ingest.descriptors import PipelineDescriptor, fields_from_dataclass
from vera_ingest.pipeline import (
    IngestPipeline,
    UnknownIngestPipelineError,
    register_ingest_pipeline,
    register_ingest_pipeline_descriptor,
)
from vera_ingest.types import IngestRequest, IngestResult, ensure_ingest_request
from vera_ingest_pymupdf import PyMuPDFOptions, pymupdf_capabilities, run_pymupdf_pipeline

PROVIDER = "plans"

__all__ = [
    "PROVIDER",
    "PlansOptions",
    "create_descriptor",
    "create_pipeline",
    "describe_pipeline",
    "ensure_registered",
    "plans_pipeline",
]


@dataclass(frozen=True)
class PlansOptions(PyMuPDFOptions):
    """The PyMuPDF settings plus drawn-text OCR."""

    options_label = "Plans"

    ocr_drawn_text: str = field(
        default="auto",
        metadata={
            "label": "Drawn-text OCR",
            "type": "enum",
            "description": (
                "OCR low-text sheets whose lettering is drawn as vectors or "
                "pasted as several images. Auto keeps the real text and adds "
                "the new words. Off leaves those sheets on the text layer. "
                "Scanned-page OCR stays under OCR mode."
            ),
            "choices": (("auto", "Auto"), ("off", "Off")),
        },
    )


def plans_pipeline(source_path: str, options: IngestRequest) -> IngestResult:
    """Convert a drawing set with drawn-text OCR and searchable detail titles."""
    request = ensure_ingest_request(options)
    config = PlansOptions.from_mapping(request.pipeline_options)
    return run_pymupdf_pipeline(
        source_path,
        request,
        config,
        parser_name=PROVIDER,
        ocr_drawn_text=config.ocr_drawn_text,
        headings_in_text=True,
    )


def _check_variant(variant: str | None) -> None:
    normalized = (variant or "default").strip().lower()
    if normalized not in {"", "default"}:
        raise UnknownIngestPipelineError(
            f"Unknown plans pipeline variant {variant!r}; use 'plans'."
        )


def describe_pipeline(variant: str = "default") -> PipelineDescriptor:
    """Return GUI/CLI metadata without opening a PDF."""
    _check_variant(variant)
    return PipelineDescriptor(
        provider=PROVIDER,
        variant="",
        spec=PROVIDER,
        label="plans — construction plan sheets",
        description=(
            "PyMuPDF pipeline for drawing sets. Also OCRs sheets whose "
            "lettering is drawn linework, and keeps detail titles in the "
            "searchable text."
        ),
        capabilities=pymupdf_capabilities(),
        fields=fields_from_dataclass(PlansOptions),
    )


def create_pipeline(variant: str = "default") -> IngestPipeline:
    """Entry-point factory for ``vera.ingest_pipelines`` provider ``plans``."""
    _check_variant(variant)
    return plans_pipeline


def create_descriptor(variant: str = "default") -> PipelineDescriptor:
    """Entry-point factory for ``vera.ingest_pipeline_descriptors``."""
    return describe_pipeline(variant)


def ensure_registered(*, replace: bool = True) -> None:
    """Register ``plans`` for callers that import this package without its metadata."""
    register_ingest_pipeline(PROVIDER, create_pipeline, replace=replace)
    register_ingest_pipeline_descriptor(PROVIDER, create_descriptor, replace=replace)
