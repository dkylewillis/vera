# vera-ingest

`vera-ingest` publishes the `vera_ingest` Python package. It depends on
`vera-doc` and owns the ingest-pipeline registry, shared descriptors and
types, conversion orchestration, reusable chunking helpers, and
ingest-produced viewer helpers.

PDF parsing and OCR live in provider plugins that register through the
`vera.ingest_pipelines` entry-point group. The default
[`vera-ingest-pymupdf`](vera-ingest-pymupdf.md) package provides the `pymupdf`
pipeline; [`vera-ingest-docling`](vera-ingest-docling.md) provides Docling's
hybrid chunker.

Pipelines return a normalized `IngestResult`. Shared `convert()` writes
validated archives through one atomic path and emits ready-made `ChunkRecord`
values plus optional attachments via `VeraDocument`. Viewer helpers under
`vera_ingest.viewer` read those ingest conventions back out for CLI, MCP, and
app consumers.

## Install

From PyPI:

```bash
python -m pip install "vera-ingest>=0.3.0"
```

For PDF conversion, also install a pipeline plugin (`vera-cli` and `vera-app`
depend on `vera-ingest-pymupdf` by default):

```bash
python -m pip install "vera-ingest-pymupdf>=0.3.0"
```

From a repository checkout:

```bash
python -m pip install ./packages/vera-doc ./packages/vera-ingest ./packages/vera-ingest-pymupdf
```

Python 3.10 or newer is required. Core `vera-ingest` does not pull in PyMuPDF
or pdfplumber; those arrive with the pipeline plugin.

## Start here

```python
from vera_ingest import convert

convert(
    "manual.pdf",
    "manual.vera",
    parser="pymupdf",
    pipeline_options={"ocr_mode": "auto"},
    model="hashing",
    store_original=True,
)
```

Pass `embedding_function=` for a custom embedder, or use a
`provider:model-id` model spec resolved by `vera_doc.get_embedder`. New callers
should pass `parser`, `pipeline_options`, and embedder settings
(`model` / `embedding_function` / `embedder_options`); legacy
kwargs such as `chunk_size` and `ocr_mode` remain compatibility aliases
forwarded only when explicitly provided. Omitted aliases mean the pipeline's
own default.

## Concepts

- **Pipeline registry** discovers installed providers via entry points
  (`vera.ingest_pipelines`) or in-process `register_ingest_pipeline()`.
  Specs resolve as `provider[:variant]` with no silent fallback. Registry and
  descriptor APIs are experimental and may change before 1.0.
- **Pipeline-owned config** keeps typed defaults, validation, and field
  descriptors inside each ingest plugin; shared convert passes a thin
  `IngestRequest` with opaque `pipeline_options`.
- **Chunking helpers** remain available for providers that want sliding-window
  behavior (whitespace-split words, not characters) without owning the writer.
- **Atomic conversion** validates a temporary archive before publishing it.

## Documentation

- [Convert documents](../conversion.md) — OCR, chunking, embedding, and batch conversion.
- [Creating an ingest pipeline plugin](../creating-an-ingest-pipeline.md) — write and register
  a new pipeline provider.
- [Figures and regions](../figures-and-regions.md) — extracted visual metadata and
  [schema storage map](../figures-and-regions.md#storage-map-vera-02-schema).
- [Conversion recipes](../examples.md) — single files, scans, and nested libraries.
- [Python conversion example](../python-api.md#pdf-extraction).

## API reference

- [`vera_ingest`](../reference/vera-ingest.md) — curated public conversion,
  ingest-pipeline registry, page/block types, and chunking interfaces.
