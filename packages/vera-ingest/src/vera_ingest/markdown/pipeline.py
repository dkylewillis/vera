"""Markdown ingest pipeline for VERA."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from ..chunking import build_chunks_from_blocks
from ..types import (
    IngestBlock,
    IngestChunk,
    IngestRequest,
    IngestResult,
    ensure_ingest_request,
)
from .options import MarkdownOptions, describe_pipeline
from .parser import parse_markdown

__all__ = ["markdown_pipeline", "MarkdownOptions", "describe_pipeline"]


def _package_version() -> str:
    try:
        return version("vera-ingest")
    except PackageNotFoundError:  # pragma: no cover - editable/source runs
        return "unknown"


def markdown_pipeline(source_path: str, options: IngestRequest) -> IngestResult:
    """Heading-aware ingest pipeline for Markdown sources."""
    request = ensure_ingest_request(options)
    config = MarkdownOptions.from_mapping(request.pipeline_options)
    text = Path(source_path).read_text(encoding="utf-8", errors="replace")
    pages, parsed = parse_markdown(text)
    block_records = [
        (
            f"block_{index:06d}",
            IngestBlock.from_parsed(f"block_{index:06d}", item.parsed, regions=[item.region()]),
        )
        for index, item in enumerate(parsed, start=1)
    ]
    chunks = build_chunks_from_blocks(
        [(block_id, block) for block_id, block in block_records],
        chunk_size=config.chunk_size,
        overlap=config.overlap,
    )
    return IngestResult(
        pages=pages,
        blocks=[block for _, block in block_records],
        chunks=[
            IngestChunk(
                chunk_id=f"chunk_{index:06d}",
                text=chunk.text,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                heading_path=chunk.heading_path,
                token_count=chunk.token_count,
                block_ids=list(chunk.block_ids),
            )
            for index, chunk in enumerate(chunks, start=1)
        ],
        parser_name="markdown",
        parser_version=_package_version(),
        chunking_strategy=f"heading_block_sliding_window:{config.chunk_size}:{config.overlap}",
    )
