# Python API

## Install

Install only the storage and search engine:

```bash
python -m pip install "vera-doc>=0.2.2"
```

Install source ingestion separately when needed:

```bash
python -m pip install "vera-ingest>=0.2.2"
```

`vera-ingest` may not yet be published to PyPI. If the install fails because the
package cannot be found, install from a repository checkout instead
(`python -m pip install ./packages/vera-doc ./packages/vera-ingest`).

## Create and search a database

`vera-doc` accepts final chunks. It never parses or chunks source files.

```python
from vera import ChunkRecord, VeraDocument

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
        print(result.score, result.record.text)
```

`create()` refuses to overwrite an existing path unless `overwrite=True`.
`open()` defaults to read-only mode; use `mode="write"` for mutations.
Both accept `str` and path-like values and support context managers.

## Records

```python
from vera import AttachmentRef, ChunkRecord

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
database dimension. When `vector` is omitted, the configured embedding
function embeds the text.

## Add, upsert, get, and delete

```python
from vera import ChunkRecord, VeraDocument

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
atomic.

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
from vera import AttachmentRecord, AttachmentRef, ChunkRecord, VeraDocument

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
    )
```

Pass `vector=[...]` instead of text for vector-only semantic search. Portable
metadata filtering currently supports exact equality on top-level keys.

## Database metadata, inspection, and validation

```python
with VeraDocument.open("manual.vera") as document:
    print(document.metadata)
    print(document.inspect())
    report = document.validate()
    assert report["ok"], report["issues"]
```

Archive metadata is caller-controlled JSON. Format, embedding model, dimension,
record counts, and integrity results are available through `inspect()` and
`validate()`.

## PDF extraction

Conversion is not part of `vera-doc`:

```python
from vera_ingest import batch_convert, convert

convert(
    "input.pdf",
    "output.vera",
    model="hashing",
    chunk_size=500,
    overlap=75,
    store_original=True,
    ocr_mode="auto",
)
```

`vera-ingest` parses and chunks the source, creates `ChunkRecord` objects and
optional attachments, then writes them through `VeraDocument`.

## Corpus and library indexes

```python
from vera import VeraCorpus, build_library_index, update_library_index

build_library_index("./library", recursive=True)

with VeraCorpus.open("./library") as corpus:
    results = corpus.search("detention requirements", top_k=5)

update_library_index("./library")
```

The `.vera-index/` directory is derived and rebuildable. The `.vera` files
remain the source of truth.

## Evaluation and MCP

Evaluation belongs to `vera-cli`:

```python
from vera_cli.evaluate import evaluate
```

MCP belongs to the separately installable `vera-mcp` package:

```python
from vera_mcp import build_server
```
