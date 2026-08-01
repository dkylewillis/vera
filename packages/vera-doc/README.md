# vera-doc

`vera-doc` is VERA's embedded storage and search engine. It stores ready-made
text chunks in a portable SQLite `.vera` file and provides transactional CRUD,
embeddings, metadata filters, keyword search, vector search, hybrid search,
corpus search, and rebuildable library indexes.

It intentionally contains no PDF parsing, OCR, source extraction, chunking,
MCP, CLI, or desktop dependencies. Applications extract and chunk content
before calling `vera-doc`. The separate `vera-extract` package provides the
standard PDF pipeline.

## Install

```bash
python -m pip install vera-doc
```

Python 3.10 or newer is required. The default hashing embedder needs no model
download or API key.

## Quick start

```python
from vera import ChunkRecord, VeraDatabase

records = [
    ChunkRecord(
        id="pipe-requirement",
        text="The minimum pipe diameter is 12 inches.",
        metadata={
            "source_filename": "manual.pdf",
            "page_start": 42,
            "heading_path": "Chapter 4 > Pipe Design",
        },
    )
]

with VeraDatabase.create("manual.vera") as database:
    database.add(records)

with VeraDatabase.open("manual.vera") as database:
    results = database.search(
        text="minimum pipe size",
        mode="hybrid",
        top_k=5,
    )

for result in results:
    print(result.score, result.record.text)
```

`VeraDatabase.open()` is read-only by default. Use `mode="write"` when adding,
updating, or deleting records.

## What is stored in a `.vera` file?

A VERA 0.2 file is one SQLite database containing:

```text
manual.vera
├── vera_metadata       Format, embedding configuration, archive metadata
├── chunks              Final searchable text and JSON metadata
├── embeddings          One float32 vector per chunk
├── chunks_fts          SQLite FTS5 keyword index
├── attachments         Optional opaque binary payloads
└── chunk_attachments   Typed links from chunks to attachments
```

The core schema is conceptually:

```sql
CREATE TABLE chunks (
    chunk_id      TEXT PRIMARY KEY,
    text          TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE embeddings (
    chunk_id        TEXT PRIMARY KEY REFERENCES chunks(chunk_id),
    model_name      TEXT NOT NULL,
    model_dimension INTEGER NOT NULL,
    vector          BLOB NOT NULL,
    vector_format   TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE TABLE attachments (
    attachment_id TEXT PRIMARY KEY,
    mime_type     TEXT NOT NULL,
    filename      TEXT,
    data          BLOB NOT NULL,
    hash          TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at    TEXT NOT NULL
);
```

Pages, headings, citations, bounding boxes, and source identity are optional
chunk metadata. Original files and extracted images may be stored as opaque
attachments. `vera-doc` stores these values but does not interpret or extract
them.

## Public objects

### `ChunkRecord`

The only indexed record type:

```python
ChunkRecord(
    id: str,
    text: str,
    metadata: Mapping[str, JSONValue] = {},
    vector: Sequence[float] | None = None,
    attachments: tuple[AttachmentRef, ...] = (),
)
```

- `id` is a non-empty caller-controlled identifier.
- `text` is final chunk text. `vera-doc` never splits or cleans it.
- `metadata` may contain any JSON-compatible object.
- `vector` may contain a precomputed embedding. When omitted, the configured
  embedding function embeds `text`.
- `attachments` links the chunk to stored attachments.

Records are immutable. IDs, text, metadata, vectors, and attachment references
are validated when the object is created or written.

### `AttachmentRecord`

An optional opaque binary payload:

```python
AttachmentRecord(
    id: str,
    data: bytes,
    media_type: str,
    filename: str | None = None,
    checksum: str | None = None,
    metadata: Mapping[str, JSONValue] = {},
)
```

The SHA-256 checksum is computed automatically. If a checksum is supplied, it
must match the bytes. Attachments are not embedded or searchable.

### `AttachmentRef`

Links a chunk to an attachment:

```python
AttachmentRef(
    attachment_id="source-pdf",
    role="source",
)
```

The role is caller-defined. Common roles include `source`, `figure`, and
`viewer_data`.

### `QueryResult`

Returned by `VeraDatabase.search()`:

```python
QueryResult(
    record: ChunkRecord,
    score: float,
    semantic_score: float | None,
    keyword_score: float | None,
)
```

Call `result.as_dict()` for a JSON-compatible result without the raw vector.

### `EmbeddingFunction`

A structural protocol for custom embedders:

```python
class EmbeddingFunction:
    model_name: str
    dimension: int

    def embed(self, texts: list[str]) -> numpy.ndarray:
        ...
```

The same model and dimension must be used for stored records and text queries.

## `VeraDatabase` methods

### Create and open

```python
VeraDatabase.create(
    path,
    *,
    embedding_function=None,
    model="hashing",
    metadata=None,
    overwrite=False,
)

VeraDatabase.open(
    path,
    *,
    mode="read",
    embedding_function=None,
)
```

`create()` publishes a valid database atomically. It raises `FileExistsError`
unless `overwrite=True`. Both methods return context managers.

### Add records

```python
database.add(records)
```

Inserts an iterable of `ChunkRecord` objects. Existing IDs raise
`DuplicateRecordError`. The chunk row, embedding, FTS row, and attachment links
are written in one transaction.

### Insert or replace records

```python
database.upsert(records)
```

Inserts new IDs and replaces existing records. Replacement updates text,
metadata, embedding, keyword index, and attachment links together.

### Retrieve records

```python
database.get(
    ids=None,
    *,
    where=None,
    limit=None,
)
```

Returns `ChunkRecord` objects, including their vectors and attachment links.
`where` performs exact equality matching on top-level metadata keys:

```python
records = database.get(where={"discipline": "civil"})
```

### Delete records

```python
deleted_count = database.delete(
    ids=None,
    *,
    where=None,
)
```

Deleting a chunk also deletes its embedding, keyword-index row, and attachment
links. It does not delete the attachments themselves.

### Search

```python
database.search(
    *,
    text=None,
    vector=None,
    mode="hybrid",
    where=None,
    top_k=10,
)
```

Supported modes:

- `keyword` uses SQLite FTS5 and BM25 ranking.
- `semantic` uses cosine similarity against stored vectors.
- `hybrid` independently normalizes semantic and keyword scores, then combines
  them with equal weight.

Semantic search accepts query `text` or a compatible precomputed `vector`.
Keyword and hybrid search require text.

### Attachments

```python
database.put_attachments(attachments, upsert=False)
attachment = database.get_attachment("source-pdf")
database.delete_attachment("source-pdf")
```

Referenced attachments cannot be deleted until their chunk links are removed.
Missing attachments raise `RecordNotFoundError`.

### Archive metadata

```python
metadata = database.metadata
database.set_metadata({"project": "stormwater"})
```

Archive metadata is a JSON-compatible object separate from per-chunk metadata.

### Transactions

```python
with database.transaction():
    database.put_attachments(attachments)
    database.add(records)
```

The entire block commits together. An exception rolls it back. Nested
transactions are intentionally rejected.

### Inspection and validation

```python
info = database.inspect()
report = database.validate()
```

Inspection reports the format, model, dimension, counts, and archive metadata.
Validation checks SQLite integrity, required tables and metadata, embedding and
FTS parity, vector lengths, JSON payloads, foreign keys, and attachment hashes.

### Close

```python
database.close()
```

Context managers call `close()` automatically.

## Exceptions

- `DuplicateRecordError` — `add()` received an existing ID.
- `RecordNotFoundError` — a chunk references an unknown attachment or a
  requested attachment does not exist.
- `ReadOnlyError` — a mutation was attempted after a read-only open.
- Standard `FileNotFoundError`, `FileExistsError`, `TypeError`, and
  `ValueError` are used for ordinary path and validation failures.

## Optional attachments example

```python
from vera import (
    AttachmentRecord,
    AttachmentRef,
    ChunkRecord,
    VeraDatabase,
)

source = AttachmentRecord(
    id="source-pdf",
    data=pdf_bytes,
    media_type="application/pdf",
    filename="manual.pdf",
    metadata={"role": "source"},
)

chunk = ChunkRecord(
    id="chunk-1",
    text="The final, already-extracted chunk.",
    metadata={"page_start": 42},
    attachments=(AttachmentRef("source-pdf", role="source"),),
)

with VeraDatabase.create("manual.vera") as database:
    with database.transaction():
        database.put_attachments([source])
        database.add([chunk])
```

## Custom embeddings

```python
import numpy as np

from vera import ChunkRecord, VeraDatabase


class MyEmbedder:
    model_name = "example/my-embedder"
    dimension = 2

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.asarray([[1.0, 0.0] for _ in texts], dtype=np.float32)


embedder = MyEmbedder()

with VeraDatabase.create(
    "custom.vera",
    embedding_function=embedder,
) as database:
    database.add([ChunkRecord(id="one", text="Example text")])

with VeraDatabase.open(
    "custom.vera",
    embedding_function=embedder,
) as database:
    results = database.search(text="example", mode="semantic")
```

Callers may instead provide `ChunkRecord.vector` and search with a query
vector.

## Libraries of `.vera` files

`VeraCorpus` searches a directory of `.vera` files as one corpus:

```python
from vera import VeraCorpus

with VeraCorpus.open("./library", recursive=True) as corpus:
    results = corpus.search("detention requirements", top_k=5)
```

For larger libraries, create a persistent derived index:

```python
from vera import (
    build_library_index,
    library_index_status,
    update_library_index,
)

build_library_index("./library", recursive=True)
print(library_index_status("./library"))
update_library_index("./library")
```

The `.vera-index/` directory is rebuildable. Individual `.vera` files remain
the source of truth.

## Legacy document API

`VeraDocument` remains a read-oriented compatibility facade for VERA 0.1,
the CLI, the desktop app, and citation-oriented workflows:

```python
from vera import VeraDocument

with VeraDocument.open("manual.vera") as document:
    results = document.search(
        "detention requirements",
        mode="hybrid",
        top_k=5,
        context_chunks=1,
    )
```

New applications that create or mutate databases should use `VeraDatabase`.

## Package source structure

```text
src/vera/
├── __init__.py          Public exports
├── models.py            Chunk, attachment, and query value objects
├── database.py          Transactional vector-database facade
├── document.py          Legacy/read-oriented compatibility facade
├── corpus.py            Multi-file corpus search
├── collection.py        Persistent library index
└── core/
    ├── schema.py        SQLite schema and format versions
    ├── validation.py    Integrity and contract validation
    ├── embeddings.py    Embedders and vector serialization
    ├── search.py        Legacy search implementation
    ├── inspection.py    Legacy inspection helpers
    ├── access.py        Legacy page/asset/region access
    └── figures.py       Legacy figure access
```

Source extraction lives under `packages/vera-extract`, and MCP integration
lives under `packages/vera-mcp`.

## Format and API references

- [VERA 0.2 specification](https://github.com/dkylewillis/vera/blob/main/docs/vera-spec-v0.2.md)
- [Full Python API guide](https://github.com/dkylewillis/vera/blob/main/docs/python-api.md)
- [Architecture](https://github.com/dkylewillis/vera/blob/main/docs/architecture.md)
