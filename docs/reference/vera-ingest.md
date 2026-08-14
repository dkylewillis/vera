# vera_ingest package

PDF parsing, chunking, and conversion to `.vera` archives.

::: vera_ingest
    options:
      members:
        - convert
        - batch_convert
        - Chunk
        - ParsedBlock
        - ParsedPage
        - parse_pdf
        - parse_pdf_structured
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
interpret ingest-produced attachments and metadata. See the
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
