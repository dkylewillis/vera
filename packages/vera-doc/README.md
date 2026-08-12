# vera-doc

`vera-doc` is VERA's embedded storage and search engine. It stores ready-made
text chunks in a portable SQLite `.vera` file and provides transactional CRUD,
embeddings, metadata filters, keyword search, vector search, hybrid search,
corpus search, and rebuildable library indexes.

It intentionally contains no PDF parsing, OCR, source extraction, chunking,
MCP, CLI, or desktop dependencies. Applications extract and chunk content
before calling `vera-doc`. The separate `vera-ingest` package provides the
standard PDF pipeline.

**Documentation:** [vera-doc guides and API reference](https://dkylewillis.github.io/vera/packages/vera-doc/)

## Install

```bash
python -m pip install vera-doc
```

Python 3.10 or newer is required. The default hashing embedder needs no model
download or API key.

## Quick start

```python
from vera import ChunkRecord, VeraDocument

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

with VeraDocument.create("manual.vera") as document:
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

`VeraDocument.open()` is read-only by default. Use `mode="write"` when adding,
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

Returned by `VeraDocument.search()`:

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

## `VeraDocument` methods

### Create and open

```python
VeraDocument.create(
    path,
    *,
    embedding_function=None,
    model="hashing",
    metadata=None,
    overwrite=False,
)

VeraDocument.open(
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
document.add(records)
```

Inserts an iterable of `ChunkRecord` objects. Existing IDs raise
`DuplicateRecordError`. The chunk row, embedding, FTS row, and attachment links
are written in one transaction.

### Insert or replace records

```python
document.upsert(records)
```

Inserts new IDs and replaces existing records. Replacement updates text,
metadata, embedding, keyword index, and attachment links together.

### Retrieve records

```python
document.get(
    ids=None,
    *,
    where=None,
    limit=None,
)
```

Returns `ChunkRecord` objects, including their vectors and attachment links.
`where` performs exact equality matching on top-level metadata keys:

```python
records = document.get(where={"discipline": "civil"})
```

### Delete records

```python
deleted_count = document.delete(
    ids=None,
    *,
    where=None,
)
```

Deleting a chunk also deletes its embedding, keyword-index row, and attachment
links. It does not delete the attachments themselves.

### Search

```python
document.search(
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
document.put_attachments(attachments, upsert=False)
attachment = document.get_attachment("source-pdf")
document.delete_attachment("source-pdf")
```

Referenced attachments cannot be deleted until their chunk links are removed.
Missing attachments raise `RecordNotFoundError`.

### Archive metadata

```python
metadata = document.metadata
document.set_metadata({"project": "stormwater"})
```

Archive metadata is a JSON-compatible object separate from per-chunk metadata.

### Transactions

```python
with document.transaction():
    document.put_attachments(attachments)
    document.add(records)
```

The entire block commits together. An exception rolls it back. Nested
transactions are intentionally rejected.

### Inspection and validation

```python
info = document.inspect()
report = document.validate()
```

Inspection reports the format, model, dimension, normalization policy, counts,
and archive metadata. Validation checks SQLite integrity, required tables and
metadata, embedding and FTS parity, vector lengths, declared L2 normalization,
JSON payloads, foreign keys, and attachment hashes. Older archives without a
normalization policy report `unknown` and remain valid.

### Close

```python
document.close()
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
    VeraDocument,
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

with VeraDocument.create("manual.vera") as document:
    with document.transaction():
        document.put_attachments([source])
        document.add([chunk])
```

## Custom embeddings

Pass any object that satisfies the `EmbeddingFunction` protocol:

```python
import numpy as np

from vera import ChunkRecord, VeraDocument


class MyEmbedder:
    model_name = "example/my-embedder"
    dimension = 2

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.asarray([[1.0, 0.0] for _ in texts], dtype=np.float32)


embedder = MyEmbedder()

with VeraDocument.create(
    "custom.vera",
    embedding_function=embedder,
) as document:
    document.add([ChunkRecord(id="one", text="Example text")])

with VeraDocument.open(
    "custom.vera",
    embedding_function=embedder,
) as document:
    results = document.search(text="example", mode="semantic")
```

Callers may instead provide `ChunkRecord.vector` and search with a query
vector.

### Named providers and plugins

Built-in model specs resolve through `get_embedder()`:

| Spec | Provider |
|------|----------|
| `hashing` / `vera-hashing-384` / `hashing:vera-hashing-384` | Built-in hashing embedder |
| `sentence-transformers:all-MiniLM-L6-v2` | Sentence Transformers (`ml` extra) |
| `sentence-transformers/all-MiniLM-L6-v2` | Legacy alias for the same model |
| `all-MiniLM-L6-v2` | Legacy alias for the same model |

Unknown specs raise `UnknownEmbeddingModelError` (they no longer fall back to
hashing).

Register additional providers in-process:

```python
from vera import get_embedder, register_embedder


@register_embedder("example")
def factory(model_id: str, **config):
    return MyEmbedder()  # model_name / dimension / embed(...)


embedder = get_embedder("example:my-embedder")
```

Or ship a plugin that advertises entry points in the `vera.embedders` and
optional `vera.embedder_descriptors` groups:

```toml
[project.entry-points."vera.embedders"]
example = "my_package.embeddings:factory"

[project.entry-points."vera.embedder_descriptors"]
example = "my_package.embeddings:create_descriptor"
```

After `pip install`, `get_embedder("example:my-embedder")` resolves the factory
with no changes to `vera-doc`. Provider-owned settings use an
`EmbedderOptions` dataclass (same metadata pattern as ingest pipelines); pass
them as `embedder_options={...}`, `get_embedder(..., batch_size=64)`, or CLI
`--embedder-option KEY=VALUE`. See
[Creating an embedding provider plugin](../../docs/creating-an-embedding-provider.md).

### OpenAI embedding plugin example

VERA does not bundle hosted providers. Prefer the Options + descriptor
authoring model in
[Creating an embedding provider plugin](../../docs/creating-an-embedding-provider.md).
This minimal sketch shows the factory + entry points:

```toml
# pyproject.toml
[project]
name = "vera-openai-embeddings"
dependencies = ["openai>=1", "vera-doc"]

[project.entry-points."vera.embedders"]
openai = "vera_openai_embeddings:create_embedder"

[project.entry-points."vera.embedder_descriptors"]
openai = "vera_openai_embeddings:create_descriptor"
```

```python
# vera_openai_embeddings.py
import os

import numpy as np
from openai import OpenAI

from vera import EmbedderCapabilities, EmbedderDescriptor, EmbedderOptions
from vera.core.embedder_descriptors import fields_from_dataclass
from dataclasses import dataclass, field


@dataclass(frozen=True)
class OpenAIOptions(EmbedderOptions):
    api_key: str = field(
        default="",
        metadata={
            "label": "API key",
            "allow_empty": True,
            "description": "Optional override; otherwise uses OPENAI_API_KEY.",
        },
    )
    batch_size: int = field(
        default=128,
        metadata={"label": "Batch size", "minimum": 1, "maximum": 2048},
    )


class OpenAIEmbedder:
    normalization = "l2"

    def __init__(self, model_id: str, *, api_key: str, batch_size: int):
        self.model_name = f"openai:{model_id}"
        self._client = OpenAI(api_key=api_key or os.environ["OPENAI_API_KEY"])
        self._model = model_id
        self._batch_size = batch_size
        self.dimension = len(self.embed(["dimension probe"])[0])

    def embed(self, texts: list[str]) -> list[np.ndarray]:
        vectors = []
        for start in range(0, len(texts), self._batch_size):
            response = self._client.embeddings.create(
                model=self._model,
                input=texts[start : start + self._batch_size],
            )
            vectors.extend(item.embedding for item in response.data)
        normalized = []
        for vector in vectors:
            array = np.asarray(vector, dtype=np.float32)
            norm = np.linalg.norm(array)
            normalized.append(array / norm if norm else array)
        return normalized


def create_embedder(model_id: str, **config):
    options = OpenAIOptions.from_mapping(config)
    return OpenAIEmbedder(
        model_id,
        api_key=options.api_key,
        batch_size=options.batch_size,
    )


def create_descriptor() -> EmbedderDescriptor:
    return EmbedderDescriptor(
        provider="openai",
        label="openai — hosted embeddings",
        description="OpenAI embeddings API.",
        default_model_id="text-embedding-3-small",
        example_specs=("openai:text-embedding-3-small",),
        capabilities=EmbedderCapabilities(
            requires_network=True,
            requires_api_key=True,
            local_model=False,
        ),
        fields=fields_from_dataclass(OpenAIOptions),
    )
```

After installing the plugin and setting `OPENAI_API_KEY`, use it from the CLI:

```bash
vera convert "manual.pdf" --model openai:text-embedding-3-small \
  --embedder-option batch_size=64
```

Or pass provider-specific settings from Python:

```python
from vera import get_embedder
from vera_ingest import convert

embedder = get_embedder(
    "openai:text-embedding-3-large",
    embedder_options={"batch_size": 64},
)
convert("manual.pdf", "manual.vera", embedding_function=embedder)
```

### Claude applications

Anthropic's Claude API does not provide an embeddings endpoint. Applications
that use Claude to answer questions should use a separate embedding provider
for retrieval, such as Voyage AI. A Voyage plugin follows the same
`vera.embedders` pattern and can expose a model such as
`voyage:voyage-3`; keep that full spec as the embedder's `model_name` so search
can resolve the same provider later.

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

## Package source structure

```text
src/vera/
├── __init__.py          Public exports
├── models.py            Chunk, attachment, and query value objects
├── document.py          Storage, CRUD, search, and viewer helpers
├── corpus.py            Multi-file corpus search
├── collection.py        Persistent library index
└── core/
    ├── schema.py        SQLite schema and format version
    ├── validation.py    Integrity and contract validation
    └── embeddings.py    Embedders and vector serialization
```

Source ingestion lives under `packages/vera-ingest`, and MCP integration
lives under `packages/vera-mcp`.

## Format and API references

- [VERA 0.2 specification](https://github.com/dkylewillis/vera/blob/main/docs/vera-spec-v0.2.md)
- [Full Python API guide](https://github.com/dkylewillis/vera/blob/main/docs/python-api.md)
- [Architecture](https://github.com/dkylewillis/vera/blob/main/docs/architecture.md)
