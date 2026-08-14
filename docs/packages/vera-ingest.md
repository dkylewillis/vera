# vera-ingest

`vera-ingest` publishes the `vera_ingest` Python package. It depends on
`vera-doc` and owns PDF parsing, selective OCR, table extraction, heading
detection, chunking, and conversion into validated `.vera` archives.

It produces ready-made `ChunkRecord` values and optional attachments, then
writes them through `VeraDocument`. Viewer helpers under `vera_ingest.viewer`
read those ingest conventions back out for CLI, MCP, and app consumers.

## Install

From PyPI:

```bash
python -m pip install "vera-ingest>=0.2.5"
```

`vera-ingest` may not yet be published to PyPI. If the install fails because the
package cannot be found, install from a repository checkout instead:

```bash
python -m pip install ./packages/vera-doc ./packages/vera-ingest
```

Python 3.10 or newer is required. PyMuPDF and pdfplumber are installed with the
package. Default English OCR works locally with bundled language data.

## Start here

```python
from vera_ingest import convert

convert(
    "manual.pdf",
    "manual.vera",
    model="hashing",
    ocr_mode="auto",
    store_original=True,
)
```

## Concepts

- **Extraction** identifies page text, layout blocks, headings, tables, images,
  and captions.
- **Selective OCR** retains native text where possible and recognizes
  image-based low-text pages.
- **Chunking** produces page-bounded text records with citation metadata.
- **Atomic conversion** validates a temporary archive before publishing it.

The package currently supports the `pymupdf` parser. OCR is designed for
scanned prose; it does not reconstruct complex scanned forms or tables.

## Documentation

- [Convert documents](../conversion.md) — OCR, chunking, embedding, and batch conversion.
- [Figures and regions](../figures-and-regions.md) — extracted visual metadata and
  [schema storage map](../figures-and-regions.md#storage-map-vera-02-schema).
- [Conversion recipes](../examples.md) — single files, scans, and nested libraries.
- [Python conversion example](../python-api.md#pdf-extraction).

## API reference

- [`vera_ingest`](../reference/vera-ingest.md) — curated public conversion,
  parser, page, block, and chunking interfaces.
