# Python API

## Install

Install only the storage and search engine:

```bash
python -m pip install "vera-doc>=0.3.0"
```

Install source ingestion separately when needed:

```bash
python -m pip install "vera-ingest>=0.3.0"
python -m pip install "vera-ingest-pymupdf>=0.3.0"
```

## Create and search a database

`vera-doc` accepts final chunks. It never parses or chunks source files.

```python
from vera_doc import ChunkRecord, VeraDocument

records = [
    ChunkRecord(
        id="requirements-1",
        text="The minimum pipe diameter is 12 inches.",
        metadata={
            "source_filename": "manual.pdf",
            "page_start": 42,
            "heading_path": "Chapter 4 > Pipe Design",
        },
    )
]

with VeraDocument.create(
    "manual.vera",
    metadata={"project": "drainage"},
) as document:
    document.add(records)

with VeraDocument.open("manual.vera") as document:
    results = document.search(
        text="minimum pipe size",
        mode="hybrid",
        top_k=5,
    )
    for result in results:
        print(result.score, result.citation.page_start, result.record.text)
```

`create()` refuses to overwrite an existing path unless `overwrite=True`.
`open()` defaults to read-only mode; use `mode="write"` for mutations.
Both accept `str` and path-like values and support context managers.
New archives also record their stored-vector normalization policy. Built-in
embedders declare `l2`; custom embedders may expose a `normalization` attribute
or callers can set `embedding_normalization="l2"`, `"none"`, or `"unknown"`:

```python
with VeraDocument.create(
    "external-vectors.vera",
    embedding_function=my_embedder,
    embedding_normalization="none",
) as document:
    ...
```

Embedders without a declaration default to `unknown`. Under the `l2` policy,
non-zero precomputed and generated vectors must have unit L2 norm.

## Records

```python
from vera_doc import AttachmentRef, ChunkRecord

record = ChunkRecord(
    id="chunk-1",
    text="Final text supplied by the caller.",
    metadata={"source": "manual.pdf", "page": 12},
    vector=None,
    attachments=(AttachmentRef("source", role="source"),),
)
```

`ChunkRecord` is immutable. Its ID and text must be non-empty, metadata must be
JSON-compatible, and a supplied vector must contain finite numbers matching the
database dimension and declared normalization policy. When `vector` is omitted,
the configured embedding function embeds the text.

## Add, upsert, get, and delete

```python
from vera_doc import ChunkRecord, VeraDocument

with VeraDocument.open("manual.vera", mode="write") as document:
    document.add([ChunkRecord(id="new", text="New chunk")])

    document.upsert([
        ChunkRecord(
            id="new",
            text="Replacement text",
            metadata={"status": "reviewed"},
        )
    ])

    reviewed = document.get(where={"status": "reviewed"})
    deleted_count = document.delete(ids=["new"])
```

`add()` rejects existing IDs. `upsert()` inserts or replaces the text,
metadata, vector, FTS row, and attachment links together. Batch writes are
atomic. New archives write `chunks_fts.rowid` equal to `chunks.rowid`.
Archives written before that alignment stay writable: deletes fall back to
`chunk_id`, and inserts append when another chunk already occupies the
matching FTS rowid. Alignment is an optimization, not a format 0.2
requirement.

Use an explicit transaction to combine operations:

```python
with VeraDocument.open("manual.vera", mode="write") as document:
    with document.transaction():
        document.put_attachments(attachments)
        document.add(records)
```

An exception rolls the transaction back.

## Optional attachments

Attachments are opaque bytes. `vera-doc` stores and retrieves them but does not
parse, OCR, chunk, embed, or search them.

```python
from vera_doc import AttachmentRecord, AttachmentRef, ChunkRecord, VeraDocument

source = AttachmentRecord(
    id="source",
    data=pdf_bytes,
    media_type="application/pdf",
    filename="manual.pdf",
    metadata={"role": "source"},
)

record = ChunkRecord(
    id="chunk-1",
    text="Ready-made searchable text.",
    attachments=(AttachmentRef("source", role="source"),),
)

with VeraDocument.create("manual.vera") as document:
    with document.transaction():
        document.put_attachments([source])
        document.add([record])
```

Referenced attachments cannot be deleted until their links are removed.
Checksums are computed and validated automatically.

Use `attachment_metadata()` when attachment IDs, MIME types, filenames,
checksums, byte sizes, and metadata are needed without reading binary payloads:

```python
with VeraDocument.open("manual.vera") as document:
    descriptors = document.attachment_metadata(
        ["image_block_000042"],
        where={"role": "figure"},
    )
```

The returned descriptors include `size` (payload length in bytes) and do not contain a `data` field. Call `get_attachment()` only for the IDs whose bytes are actually needed, or `write_attachment()` to copy those bytes to a file.

## Search modes and filters

```python
with VeraDocument.open("manual.vera") as document:
    keyword = document.search(
        text="section 4.2",
        mode="keyword",
        where={"discipline": "civil"},
    )
    semantic = document.search(
        text="how large should the pond be",
        mode="semantic",
    )
    hybrid = document.search(
        text="detention requirements",
        mode="hybrid",
        semantic_weight=0.7,
        keyword_weight=0.3,
    )
```

Hybrid search defaults to equal semantic and keyword weights. Each hit
exposes `result.citation` (`page_start`, `page_end`, `heading_path`,
`source_filename`, `document_id`) derived from chunk metadata. Pass
`vector=[...]` instead of text for vector-only semantic search. Portable
metadata filtering currently supports exact equality on top-level keys.

## Database metadata, inspection, and validation

```python
with VeraDocument.open("manual.vera") as document:
    print(document.metadata)
    print(document.inspect())
    report = document.validate()
    assert report["ok"], report["issues"]
```

Archive metadata is caller-controlled JSON. Format, embedding model and
dimension, archive byte size, record counts, and integrity results are
available through `inspect()` and `validate()`. Ingest-created archives also
expose parser, chunking, and OCR diagnostics through their metadata.

Library indexing uses two bulk-read helpers that avoid constructing
`ChunkRecord` objects and do not load attachments:

```python
with VeraDocument.open("manual.vera") as document:
    header = document.format_metadata()
    for row in document.iter_raw_chunks():
        chunk_id = row["chunk_id"]
        text = row["text"]
        model_name = row["model_name"]
        dimension = row["model_dimension"]
        vector = row["vector"]
```

`format_metadata()` returns the `vera_metadata` key/value header. Each
`iter_raw_chunks()` row includes `chunk_id`, `text`, `metadata_json`,
`model_name`, `model_dimension`, and raw `vector` bytes.

## PDF extraction

Conversion is not part of `vera-doc`:

```python
from vera_ingest import convert

convert(
    "input.pdf",
    "output.vera",
    parser="pymupdf",
    pipeline_options={"chunk_size": 700, "ocr_mode": "force"},
    model="hashing",
    # embedder_options={"device": "cpu"},
    # Legacy compatibility aliases (forwarded when advertised by the pipeline):
    # chunk_size=500, overlap=75, ocr_mode="auto", ocr_language="eng",
)
```

New callers should pass `parser`, `pipeline_options`, and embedder settings
(`model` / `embedding_function` / `embedder_options`). `model` accepts
`provider:model-id` specs (and legacy aliases). Pass
`embedding_function=` instead when you already have an embedder object.
Unknown model names raise `UnknownEmbeddingModelError` before parsing begins.
Call `preflight_embedder(model)` yourself when you need credential-env checks
before PDF work; `convert()` does not call it. Failed `vera.embedders` entry
points are listed by `vera_doc.embeddings.list_embedder_load_errors()` until
`reset_embedding_registry()` runs.
`parser` accepts ingest pipeline specs `provider[:variant]` (default
`pymupdf`). Optional plugins such as
`vera-ingest-docling` register additional
providers; unknown pipelines raise `UnknownIngestPipelineError`.
Legacy kwargs (`chunk_size`, `overlap`, `ocr_mode`, `ocr_language`, `ocr_dpi`,
`ocr_download`) remain compatibility aliases. They are forwarded only when
explicitly provided; omitted aliases mean the pipeline's own default (so a
plugin `chunk_size` of 2000 is not overwritten by 500). The CLI still passes
its argparse defaults. Sliding-window chunking clamps `overlap` to
`chunk_size - 1` so carry never overruns.

Shared convert builds a thin `IngestRequest` and merges legacy kwargs with
`pipeline_options` according to each pipeline's descriptor. Explicit
`pipeline_options` always win. Pipelines own typed defaults and validation
(PyMuPDF: whitespace-split word chunk size/overlap/OCR/DPI; Docling: whitespace-token `chunk_size`, OCR mode,
and language — no overlap/DPI).

`vera-ingest` resolves the pipeline and embedder, parses and chunks the source,
creates `ChunkRecord` objects and optional attachments, then writes them through
`VeraDocument`.

Registry and descriptor APIs (`register_ingest_pipeline`, `register_embedder`,
and their describe/list helpers) are experimental and may change before 1.0.
Hosted embedding providers (OpenAI, Voyage, Ollama) are examples you can
implement yourself; they are not bundled with VERA. See
[Creating an ingest pipeline plugin](creating-an-ingest-pipeline.md) and
[Creating an embedding provider plugin](creating-an-embedding-provider.md).

## Corpus and library indexes

```python
from vera_doc import VeraCorpus, build_library_index, update_library_index

build_library_index("./library", recursive=True)

with VeraCorpus.open("./library") as corpus:
    results = corpus.search("detention requirements", top_k=5)

update_library_index("./library")
```

The `.vera-index/` directory is derived and rebuildable. The `.vera` files
remain the source of truth. A successful `build_library_index` deletes every
other generation directory after swapping `current.json`.

## Evaluation and MCP

Evaluation belongs to `vera-cli` and opens one `.vera` archive (not a
directory):

```python
from vera_cli.evaluate import evaluate
```

MCP belongs to the separately installable `vera-mcp` package:

```python
from vera_mcp import build_server
```

## Figures

List stored figure metadata or write image files:

```python
from vera_doc import VeraDocument
from vera_ingest.viewer import export_figures, figures

with VeraDocument.open("manual.vera") as document:
    listing = figures(document)
    written = export_figures(document, "./figures")
```

`export_figures()` writes `{asset_id}.{ext}` under the directory and returns
the listing plus `path`. Requested ids that are missing or not figure
attachments raise `ValueError`. Search JSON and MCP `vera_figures` stay
metadata-only; MCP `vera_get_figure` returns native image content.
