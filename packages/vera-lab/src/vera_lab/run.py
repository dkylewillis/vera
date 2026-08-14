"""Live pipeline runs for the ingest lab."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vera_ingest.descriptors import PipelineDescriptor
from vera_ingest.pipeline import (
    describe_ingest_pipeline,
    get_ingest_pipeline,
    invoke_ingest_pipeline,
    parse_ingest_pipeline_spec,
)
from vera_ingest.types import IngestRequest, IngestResult
from vera_lab.model import LabDocument, lab_document_from_ingest_result


def parse_pipeline_option_value(raw: str) -> Any:
    """Coerce a KEY=VALUE token the same way ``vera convert`` does."""
    text = str(raw).strip()
    lowered = text.lower()
    if lowered in {"true", "yes", "y", "on"}:
        return True
    if lowered in {"false", "no", "n", "off"}:
        return False
    if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
        return int(text)
    return text


def coerce_pipeline_options(pairs: list[tuple[str, str]] | dict[str, Any] | None) -> dict[str, Any]:
    """Normalize CLI pairs or a mapping into typed pipeline options."""
    if pairs is None:
        return {}
    if isinstance(pairs, dict):
        return dict(pairs)
    options: dict[str, Any] = {}
    for key, raw in pairs:
        options[key] = parse_pipeline_option_value(raw)
    return options


def validate_pipeline_options(
    spec: str,
    pipeline_options: dict[str, Any] | None,
) -> tuple[PipelineDescriptor, dict[str, Any]]:
    """Reject unknown option keys when the descriptor advertises fields.

    Returns the descriptor and the (possibly empty) options mapping. Typed
    validation of values is left to the pipeline's ``from_mapping``.
    """
    descriptor = describe_ingest_pipeline(spec)
    options = dict(pipeline_options or {})
    allowed = descriptor.field_keys()
    if allowed and options:
        unknown = sorted(set(options) - allowed)
        if unknown:
            names = ", ".join(repr(key) for key in unknown)
            raise ValueError(
                f"Unknown pipeline option(s) for {spec!r}: {names}. "
                f"Known fields: {', '.join(sorted(allowed)) or '(none)'}."
            )
    return descriptor, options


def run_pipeline(
    source_path: str | Path,
    *,
    parser: str = "pymupdf",
    pipeline_options: dict[str, Any] | None = None,
) -> tuple[IngestResult, PipelineDescriptor, dict[str, Any]]:
    """Invoke an ingest pipeline and return the result plus resolved metadata."""
    source = Path(source_path)
    if not source.is_file():
        raise FileNotFoundError(f"Source file not found: {source}")
    descriptor, options = validate_pipeline_options(parser, pipeline_options)
    _, variant = parse_ingest_pipeline_spec(parser)
    pipeline = get_ingest_pipeline(parser)
    result = invoke_ingest_pipeline(
        pipeline,
        str(source),
        IngestRequest(variant=variant, pipeline_options=options),
    )
    return result, descriptor, options


def load_live_document(
    source_path: str | Path,
    *,
    parser: str = "pymupdf",
    pipeline_options: dict[str, Any] | None = None,
) -> LabDocument:
    """Run a pipeline and return a :class:`LabDocument`."""
    source = Path(source_path)
    result, _descriptor, options = run_pipeline(
        source,
        parser=parser,
        pipeline_options=pipeline_options,
    )
    return lab_document_from_ingest_result(
        result,
        source_path=str(source),
        source_bytes=source.read_bytes(),
        pipeline_spec=parser,
        pipeline_options=options,
    )
