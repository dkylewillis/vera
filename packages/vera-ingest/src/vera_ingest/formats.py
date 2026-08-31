"""Source-format helpers for ingest pipelines and convert discovery."""

from __future__ import annotations

import mimetypes
from pathlib import Path

from .pipeline import describe_ingest_pipeline, list_ingest_pipeline_descriptors

_PREFERRED_PROVIDERS = ("pymupdf", "markdown", "docling")

_MIME_BY_SUFFIX = {
    "pdf": "application/pdf",
    "md": "text/markdown",
    "markdown": "text/markdown",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "html": "text/html",
    "htm": "text/html",
}


def source_suffix(path: str | Path) -> str:
    """Return the lowercased extension without a leading dot."""
    return Path(path).suffix.lower().lstrip(".")


def source_mime_type(path: str | Path) -> str:
    """Return a MIME type for ``path``, preferring VERA's suffix map."""
    suffix = source_suffix(path)
    if suffix in _MIME_BY_SUFFIX:
        return _MIME_BY_SUFFIX[suffix]
    guessed = mimetypes.guess_type(Path(path).name)[0]
    return guessed or "application/octet-stream"


def pipeline_source_formats(spec: str) -> tuple[str, ...]:
    """Return the suffixes advertised by an installed pipeline spec."""
    return describe_ingest_pipeline(spec).capabilities.source_formats


def installed_source_formats() -> tuple[str, ...]:
    """Return unique suffixes advertised by installed pipelines, in first-seen order."""
    seen: list[str] = []
    for descriptor in list_ingest_pipeline_descriptors():
        if not descriptor.installed:
            continue
        for item in descriptor.capabilities.source_formats:
            if item not in seen:
                seen.append(item)
    return tuple(seen)


def pick_parser_for_suffix(suffix: str) -> str:
    """Choose an installed pipeline spec that advertises ``suffix``.

    Preference order is PyMuPDF, Markdown, then Docling, then alphabetical spec.
    """
    key = suffix.strip().lower().lstrip(".")
    matches = [
        descriptor
        for descriptor in list_ingest_pipeline_descriptors()
        if descriptor.installed and key in descriptor.capabilities.source_formats
    ]
    if not matches:
        raise ValueError(f"No installed ingest pipeline supports .{key} files.")
    by_provider = {item.provider: item for item in matches}
    for preferred in _PREFERRED_PROVIDERS:
        if preferred in by_provider:
            return by_provider[preferred].spec
    return sorted(matches, key=lambda item: item.spec)[0].spec


def resolve_ingest_parser(source: str | Path, parser: str | None = None) -> str:
    """Return the pipeline spec to use for ``source``.

    An explicit ``parser`` must advertise the file's suffix when the path has
    one. ``None`` selects an installed pipeline from the suffix.
    """
    path = Path(source)
    suffix = source_suffix(path)
    if parser and str(parser).strip():
        spec = str(parser).strip()
        formats = pipeline_source_formats(spec)
        if suffix and suffix not in formats:
            supported = ", ".join(f".{item}" for item in formats) or "(none)"
            raise ValueError(
                f"Ingest pipeline {spec!r} does not support {path.suffix} files "
                f"(supports: {supported})."
            )
        return spec
    if not suffix:
        raise ValueError(f"Cannot infer an ingest pipeline for {path.name}; pass parser=...")
    return pick_parser_for_suffix(suffix)
