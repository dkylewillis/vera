# vera-extract

`vera-extract` publishes the `vera_extract` Python package. It depends on
`vera-doc` and owns PDF parsing, selective OCR, table extraction, heading
detection, chunking, and conversion into validated `.vera` archives.

It produces ready-made `ChunkRecord` values and optional attachments, then
writes them through `VeraDatabase`.

## Install

```bash
python -m pip install ./packages/vera-doc ./packages/vera-extract
```

Python 3.10 or newer is required. PyMuPDF and pdfplumber are installed with the
package. Default English OCR works locally with bundled language data.

## Start here

```python
from vera_extract import convert

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
- [Figures and regions](../figures-and-regions.md) — extracted visual metadata.
- [Conversion recipes](../examples.md) — single files, scans, and nested libraries.
- [Python conversion example](../python-api.md#pdf-extraction).

## API reference

- [`vera_extract`](../reference/vera-extract.md) — curated public conversion,
  parser, page, block, and chunking interfaces.
