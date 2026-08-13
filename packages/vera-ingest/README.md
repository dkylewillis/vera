# vera-ingest

`vera-ingest` contains VERA's provider-neutral ingestion core: shared types,
descriptors, option parsing, a strict ingest-pipeline registry, conversion,
chunking helpers, and archive viewer conventions.

PDF conversion pipelines register through the `vera.ingest_pipelines`
entry-point group. The default `pymupdf` provider ships as
[`vera-ingest-pymupdf`](https://dkylewillis.github.io/vera/packages/vera-ingest-pymupdf/);
Docling ships as the optional
[`vera-ingest-docling`](https://dkylewillis.github.io/vera/packages/vera-ingest-docling/)
package. Pipelines return a normalized `IngestResult`; `convert()` writes
validated archives through one shared atomic path.

Each pipeline owns typed chunking/OCR defaults, validation, and a descriptor
of supported fields. New `convert()` callers should pass `parser`,
`pipeline_options`, and embedder settings (`model` / `embedding_function` /
`embedder_options`). Shared convert accepts opaque `pipeline_options` on a thin
`IngestRequest`. Legacy kwargs (`chunk_size`, `overlap`, `ocr_mode`,
`ocr_language`, `ocr_dpi`) remain compatibility aliases; descriptor fields
and OCR engine control which aliases are forwarded (Tesseract-shaped
`ocr_language`/`ocr_dpi`/`ocr_download` only go to Tesseract pipelines), and
explicit `pipeline_options` win. Omitted `convert()` aliases mean the
pipeline's own default (they are not replaced by 500/`eng`/…).

It emits ready-made `vera.ChunkRecord` values and optional opaque attachments,
then stores them through `vera.VeraDocument`. It also provides
`vera_ingest.viewer` helpers that interpret ingest-produced page, figure,
region, and source-document conventions.

## Install

```bash
python -m pip install "vera-ingest>=0.3.0"
```

For PDF conversion, also install a pipeline plugin (the CLI and desktop app
pull in `vera-ingest-pymupdf` by default):

```bash
python -m pip install "vera-ingest-pymupdf>=0.3.0"
```

From a repository checkout:

```bash
python -m pip install ./packages/vera-doc ./packages/vera-ingest ./packages/vera-ingest-pymupdf
```

See the [vera-ingest documentation](https://dkylewillis.github.io/vera/packages/vera-ingest/)
for concepts, examples, and API reference.

See the [conversion guide](https://github.com/dkylewillis/vera/blob/main/docs/conversion.md).

## Embedding model selection

`convert()` and `batch_convert()` accept either:

- `model="hashing"` / `model="sentence-transformers:all-MiniLM-L6-v2"` — resolved
  through `vera.get_embedder` before PDF parsing begins, or
- `embedding_function=<object>` — any object with `model_name`, `dimension`, and
  `embed(texts)`.

Unknown model specs raise `vera.UnknownEmbeddingModelError`. To add a named
provider without forking VERA, register a factory with
`vera.register_embedder` or ship a `vera.embedders` entry-point plugin.
