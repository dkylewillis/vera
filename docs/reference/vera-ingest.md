# vera_ingest package

Provider-neutral ingest registry, shared types, chunking helpers, and
conversion to `.vera` archives. PDF parsing/OCR live in plugins such as
[`vera-ingest-pymupdf`](../packages/vera-ingest-pymupdf.md).

::: vera_ingest
    options:
      members:
        - convert
        - batch_convert
        - Chunk
        - IngestBlock
        - IngestChunk
        - IngestRequest
        - IngestOptions
        - IngestPipeline
        - IngestResult
        - PipelineDescriptor
        - PipelineOptions
        - UnknownIngestPipelineError
        - coerce_pipeline_options
        - describe_ingest_pipeline
        - get_ingest_pipeline
        - invoke_ingest_pipeline
        - list_ingest_pipelines
        - list_ingest_pipeline_descriptors
        - prepare_pipeline_options
        - register_ingest_pipeline
        - register_ingest_pipeline_descriptor
        - ParsedBlock
        - ParsedPage
        - chunk_pages
        - build_chunks_from_blocks
        - detect_heading
        - figures
        - figures_for
        - get_page
        - get_blocks
        - get_chunk_regions
        - regions_for
        - get_source_document
        - export_source_document
      heading_level: 2
      show_if_no_docstring: true

Conversion writes through [`VeraDocument`](vera-document.md). Viewer helpers
interpret ingest-produced attachments and metadata. Shared convert accepts
opaque `pipeline_options` on a thin `IngestRequest`; pipelines own typed
defaults and descriptors. Prefer `IngestRequest` / `pipeline_options` over the
deprecated `IngestOptions` compatibility bag. See the
[conversion guide](../conversion.md) and
[figures and regions](../figures-and-regions.md).

::: vera_ingest.convert
    options:
      heading_level: 2
      show_if_no_docstring: true

::: vera_ingest.batch_convert
    options:
      heading_level: 2
      show_if_no_docstring: true
