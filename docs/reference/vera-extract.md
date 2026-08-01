# vera_extract package

PDF parsing, chunking, and conversion to `.vera` archives.

::: vera_extract
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
      heading_level: 2
      show_if_no_docstring: true

Conversion writes through [`VeraDatabase`](vera-database.md). See the
[conversion guide](../conversion.md) for OCR and batch options.

::: vera_extract.convert
    options:
      heading_level: 2
      show_if_no_docstring: true

::: vera_extract.batch_convert
    options:
      heading_level: 2
      show_if_no_docstring: true
