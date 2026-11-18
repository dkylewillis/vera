"""PyMuPDF PDF ingest pipeline for VERA."""

from __future__ import annotations

import hashlib
from importlib.metadata import PackageNotFoundError, version

from vera_ingest.chunking import build_chunks_from_blocks
from vera_ingest.types import (
    IngestBlock,
    IngestChunk,
    IngestRequest,
    IngestResult,
    ParsedBlock,
    ensure_ingest_request,
)

from .options import PyMuPDFOptions, describe_pipeline
from .parser import parse_pdf_structured

__all__ = [
    "pymupdf_pipeline",
    "run_pymupdf_pipeline",
    "PyMuPDFOptions",
    "describe_pipeline",
]


def _pymupdf_version() -> str:
    try:
        return version("PyMuPDF")
    except PackageNotFoundError:  # pragma: no cover - parser import reports the useful error
        return "unknown"


def _drop_repeated_images(
    block_records: list[tuple[str, ParsedBlock]],
) -> list[tuple[str, ParsedBlock]]:
    seen_hashes: set[str] = set()
    kept: list[tuple[str, ParsedBlock]] = []
    for block_id, block in block_records:
        if block.block_type == "image" and block.image_bytes:
            image_hash = hashlib.sha256(block.image_bytes).hexdigest()
            if image_hash in seen_hashes:
                continue
            seen_hashes.add(image_hash)
        kept.append((block_id, block))
    return kept


def pymupdf_pipeline(source_path: str, options: IngestRequest) -> IngestResult:
    """Default PDF ingest pipeline using PyMuPDF parsing and Tesseract OCR."""
    request = ensure_ingest_request(options)
    config = PyMuPDFOptions.from_mapping(request.pipeline_options)
    return run_pymupdf_pipeline(source_path, request, config, parser_name="pymupdf")


def run_pymupdf_pipeline(
    source_path: str,
    request: IngestRequest,
    config: PyMuPDFOptions,
    *,
    parser_name: str,
    ocr_drawn_text: str | None = None,
    headings_in_text: bool = False,
) -> IngestResult:
    """Parse, chunk, and package a PDF; shared by ``pymupdf`` and plugins built on it.

    ``ocr_drawn_text`` (``"auto"`` or ``"off"``) turns on the parser's
    drawn-lettering OCR and records it in the diagnostics bag; ``None`` leaves
    it off and keeps it out of the bag. ``headings_in_text`` repeats heading
    text in the chunk body so a title is searchable.
    """
    diagnostics: dict[str, object] = {}
    pages, parsed_blocks = parse_pdf_structured(
        source_path,
        ocr_mode=config.ocr_mode,
        ocr_language=config.ocr_language,
        ocr_dpi=config.ocr_dpi,
        ocr_download=config.ocr_download,
        ocr_drawn_text=ocr_drawn_text or "off",
        diagnostics=diagnostics,
        cancel=request.cancel,
    )
    if ocr_drawn_text is None:
        diagnostics.pop("ocr_drawn_text", None)
        diagnostics.pop("ocr_drawn_text_pages", None)
    block_records = _drop_repeated_images(
        [(f"block_{index:06d}", block) for index, block in enumerate(parsed_blocks, start=1)]
    )
    chunks = build_chunks_from_blocks(
        block_records,
        chunk_size=config.chunk_size,
        overlap=config.overlap,
        headings_in_text=headings_in_text,
    )
    return IngestResult(
        pages=pages,
        blocks=[IngestBlock.from_parsed(block_id, block) for block_id, block in block_records],
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
        parser_name=parser_name,
        parser_version=_pymupdf_version(),
        chunking_strategy=(f"heading_block_sliding_window:{config.chunk_size}:{config.overlap}"),
        diagnostics=diagnostics,
    )
