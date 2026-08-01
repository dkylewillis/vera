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
from .viewer import (
    export_source_document,
    figures,
    figures_for,
    get_blocks,
    get_chunk_regions,
    get_page,
    get_source_document,
    regions_for,
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
    "export_source_document",
    "figures",
    "figures_for",
    "get_blocks",
    "get_chunk_regions",
    "get_page",
    "get_source_document",
    "regions_for",
]
