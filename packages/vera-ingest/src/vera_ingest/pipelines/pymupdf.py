from __future__ import annotations

import hashlib
from importlib.metadata import PackageNotFoundError, version

from ..chunking import build_chunks_from_blocks
from ..parsers import ParsedBlock, parse_pdf_structured
from ..types import IngestBlock, IngestChunk, IngestRequest, IngestResult, coerce_ingest_request
from .pymupdf_options import PyMuPDFOptions, describe_pipeline

__all__ = ["PyMuPDFPipeline", "PyMuPDFOptions", "describe_pipeline"]


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


class PyMuPDFPipeline:
    """Compatible built-in implementation of VERA's original PDF ingestion."""

    def ingest(self, source_path: str, options: IngestRequest) -> IngestResult:
        request = coerce_ingest_request(options)
        config = PyMuPDFOptions.from_mapping(request.pipeline_options)
        diagnostics: dict[str, object] = {}
        pages, parsed_blocks = parse_pdf_structured(
            source_path,
            ocr_mode=config.ocr_mode,
            ocr_language=config.ocr_language,
            ocr_dpi=config.ocr_dpi,
            diagnostics=diagnostics,
            cancel=request.cancel,
        )
        block_records = _drop_repeated_images(
            [
                (f"block_{index:06d}", block)
                for index, block in enumerate(parsed_blocks, start=1)
            ]
        )
        chunks = build_chunks_from_blocks(
            block_records,
            chunk_size=config.chunk_size,
            overlap=config.overlap,
        )
        return IngestResult(
            pages=pages,
            blocks=[
                IngestBlock(
                    block_id=block_id,
                    page_number=block.page_number,
                    block_type=block.block_type,
                    text=block.text,
                    bbox=block.bbox,
                    heading_level=block.heading_level,
                    image_bytes=block.image_bytes,
                    image_ext=block.image_ext,
                )
                for block_id, block in block_records
            ],
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
            parser_name="pymupdf",
            parser_version=_pymupdf_version(),
            chunking_strategy=(
                f"heading_block_sliding_window:{config.chunk_size}:{config.overlap}"
            ),
            diagnostics=diagnostics,
        )
