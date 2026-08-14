"""Contributor lab for visualizing ingest pipeline layout and chunks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vera_lab.model import LabDocument
from vera_lab.report import build_report as _build_report

__all__ = [
    "LabDocument",
    "build_report",
    "__version__",
]

__version__ = "0.3.0"


def build_report(
    source: str | Path,
    output: str | Path,
    *,
    parsers: list[str] | None = None,
    pipeline_options: dict[str, Any] | None = None,
    dpi: int = 96,
    pages: str | None = None,
    max_pages: int = 25,
) -> str:
    """Build a self-contained HTML layout report for ``source``.

    ``source`` may be a PDF (live pipeline mode) or a ``.vera`` archive.
    When ``parsers`` has more than one entry, the report includes a side-by-side
    comparison. Returns the output path as a string.
    """
    return _build_report(
        source,
        output,
        parsers=parsers,
        pipeline_options=pipeline_options,
        dpi=dpi,
        pages=pages,
        max_pages=max_pages,
    )
