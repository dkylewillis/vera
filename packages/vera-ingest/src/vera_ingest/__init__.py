"""Source ingestion, chunking, and conversion adapters for VERA."""

from .chunking import (
    Chunk,
    build_chunks_from_blocks,
    chunk_pages,
    detect_heading,
)
from .convert import batch_convert, convert
from .parsers import ParsedBlock, ParsedPage, parse_pdf, parse_pdf_structured
from .pipeline import (
    IngestPipeline,
    UnknownIngestPipelineError,
    clear_ingest_pipeline_cache,
    get_ingest_pipeline,
    list_ingest_pipelines,
    register_ingest_pipeline,
    reset_ingest_pipeline_registry,
)
from .types import IngestBlock, IngestChunk, IngestOptions, IngestResult
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
    "Chunk",
    "IngestBlock",
    "IngestChunk",
    "IngestOptions",
    "IngestPipeline",
    "IngestResult",
    "ParsedBlock",
    "ParsedPage",
    "UnknownIngestPipelineError",
    "batch_convert",
    "build_chunks_from_blocks",
    "chunk_pages",
    "clear_ingest_pipeline_cache",
    "convert",
    "detect_heading",
    "export_source_document",
    "figures",
    "figures_for",
    "get_blocks",
    "get_chunk_regions",
    "get_ingest_pipeline",
    "get_page",
    "get_source_document",
    "list_ingest_pipelines",
    "parse_pdf",
    "parse_pdf_structured",
    "regions_for",
    "register_ingest_pipeline",
    "reset_ingest_pipeline_registry",
]
