"""Source extraction, chunking, and conversion adapters for VERA."""

from .convert import batch_convert, convert
from .ingest import (
    Chunk,
    ParsedBlock,
    ParsedPage,
    build_chunks_from_blocks,
    chunk_pages,
    detect_heading,
    parse_pdf,
    parse_pdf_structured,
)

__all__ = [
    "convert",
    "batch_convert",
    "Chunk",
    "ParsedBlock",
    "ParsedPage",
    "build_chunks_from_blocks",
    "chunk_pages",
    "detect_heading",
    "parse_pdf",
    "parse_pdf_structured",
]
