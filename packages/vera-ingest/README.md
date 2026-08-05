# vera-ingest

`vera-ingest` contains VERA's source ingestion stack: PDF parsing, table
extraction, selective OCR, heading detection, chunking, conversion, and a
strict ingest-pipeline registry.

Built-in conversion uses the `pymupdf` pipeline. Additional providers register
through the `vera.ingest_pipelines` entry-point group (for example the optional
`vera-ingest-docling` package). Pipelines return a normalized `IngestResult`;
`convert()` writes validated archives through one shared atomic path.

It emits ready-made `vera.ChunkRecord` values and optional opaque attachments,
then stores them through `vera.VeraDocument`. It also provides
`vera_ingest.viewer` helpers that interpret ingest-produced page, figure,
region, and source-document conventions.

## Install

```bash
python -m pip install "vera-ingest>=0.2.4"
```

`vera-ingest` may not yet be published to PyPI. If the install fails because the
package cannot be found, install from a repository checkout:

```bash
python -m pip install ./packages/vera-doc ./packages/vera-ingest
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
