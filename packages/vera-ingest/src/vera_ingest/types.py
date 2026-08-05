from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParsedPage:
    """Single page extracted from a source document."""

    page_number: int
    width: float | None
    height: float | None
    text: str


@dataclass
class ParsedBlock:
    """Legacy parser block retained as part of the public ingest API."""

    page_number: int
    block_type: str
    text: str
    bbox: tuple[float, float, float, float] | None = None
    heading_level: int | None = None
    image_bytes: bytes | None = None
    image_ext: str = ""


@dataclass
class IngestBlock:
    """Normalized layout block produced by an ingest pipeline.

    ``block_id`` must be stable for the same source and pipeline. Bounding boxes
    use page points with a top-left origin.
    """

    block_id: str
    page_number: int
    block_type: str
    text: str
    bbox: tuple[float, float, float, float] | None = None
    heading_level: int | None = None
    image_bytes: bytes | None = None
    image_ext: str = ""
    regions: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class IngestChunk:
    """Readable chunk text and its normalized provenance.

    ``embedding_text`` may provide contextualized text for embedding while
    leaving ``text`` readable and keyword-searchable in the archive.
    """

    chunk_id: str
    text: str
    page_start: int
    page_end: int
    heading_path: str
    token_count: int
    block_ids: list[str] = field(default_factory=list)
    embedding_text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class IngestOptions:
    """Common options passed to an ingest pipeline."""

    chunk_size: int = 500
    overlap: int = 75
    ocr_mode: str = "auto"
    ocr_language: str = "eng"
    ocr_dpi: int = 300
    variant: str = ""
    cancel: Any | None = None


@dataclass
class IngestResult:
    """Normalized bundle consumed by VERA's shared archive writer."""

    pages: list[ParsedPage]
    blocks: list[IngestBlock]
    chunks: list[IngestChunk]
    parser_name: str
    parser_version: str
    chunking_strategy: str
    diagnostics: dict[str, Any] = field(default_factory=dict)

