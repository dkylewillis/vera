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
    PLUGIN_API_VERSION,
    PipelineDescriptor,
    UnknownIngestPipelineError,
    describe_ingest_pipeline,
    get_ingest_pipeline,
    list_ingest_pipeline_descriptors,
    list_ingest_pipeline_load_errors,
    list_ingest_pipelines,
    register_ingest_pipeline,
    register_ingest_pipeline_descriptor,
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
    "PLUGIN_API_VERSION",
    "PipelineDescriptor",
    "UnknownIngestPipelineError",
    "convert",
    "batch_convert",
    "describe_ingest_pipeline",
    "get_ingest_pipeline",
    "list_ingest_pipeline_descriptors",
    "list_ingest_pipeline_load_errors",
    "list_ingest_pipelines",
    "register_ingest_pipeline",
    "register_ingest_pipeline_descriptor",
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
