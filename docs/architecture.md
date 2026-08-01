# VERA Architecture

## Package boundaries

VERA is a mono-repo of independently installable packages. Dependencies move
inward toward the storage and search engine:

```text
vera-extract ─┐
vera-cli ─────┼──> vera-doc
vera-app ─────┤
vera-mcp ─────┘
```

No package may make `vera-doc` depend on extraction, a user interface, MCP,
evaluation tooling, or a source-file format.

### `vera-doc`

`vera-doc` publishes the `vera` Python package. It is an embedded vector
database backed by one portable SQLite `.vera` file.

It owns:

- the current `.vera` schema and format validation;
- immutable `ChunkRecord`, `AttachmentRecord`, and query-result objects;
- transactional chunk and attachment CRUD;
- embedding generation and storage;
- keyword, semantic, and hybrid retrieval;
- read-only compatibility for 0.1 document archives;
- corpus search and rebuildable `.vera-index/` library indexes.

It does not parse, clean, OCR, or chunk source content. It does not know what a
PDF is. Attachments are opaque bytes, and chunk/archive metadata is
JSON-compatible caller data.

### `vera-extract`

`vera-extract` publishes `vera_extract`. It owns all source interpretation:

- PDF parsing and table extraction;
- selective OCR and bundled Tesseract data;
- heading detection and chunk construction;
- mapping pages, regions, figures, and provenance to chunk metadata;
- optional source/image/viewer attachments;
- single-file and batch conversion workflows.

It emits final `ChunkRecord` objects and writes them through `VeraDatabase`.
`vera-doc` never imports `vera_extract`.

### `vera-cli`

`vera-cli` publishes the `vera` console script and `vera_cli` module. It owns
argument parsing, text/JSON formatting, exit codes, and retrieval evaluation.
Conversion commands compose `vera-extract` with `vera-doc`.

### `vera-mcp`

`vera-mcp` publishes `vera_mcp` and the `vera-mcp` console script. It is a
thin MCP adapter over public `vera-doc` APIs. The optional `vera-cli[mcp]`
extra installs it for `vera mcp`.

### `vera-app`

`vera-app` owns the Electron/React desktop application, Python sidecar, viewer
interpretation, LLM providers, sessions, and application state. It depends on
both `vera-doc` and `vera-extract`, not on `vera-cli`.

## Core Python API

Applications that already have chunks need only `vera-doc`:

```python
from vera import ChunkRecord, VeraDatabase

with VeraDatabase.create("knowledge.vera") as database:
    database.add(
        [
            ChunkRecord(
                id="requirements-1",
                text="The minimum pipe diameter is 12 inches.",
                metadata={"source": "manual.pdf", "page": 42},
            )
        ]
    )

with VeraDatabase.open("knowledge.vera") as database:
    results = database.search(text="minimum pipe size", top_k=5)
```

The write API accepts only final chunks and optional opaque attachments:

```python
from vera import AttachmentRecord, AttachmentRef, ChunkRecord

source = AttachmentRecord(
    id="source",
    media_type="application/pdf",
    filename="manual.pdf",
    data=pdf_bytes,
)
record = ChunkRecord(
    id="chunk-1",
    text="Ready-made chunk text.",
    attachments=(AttachmentRef("source", role="source"),),
)
```

Extraction is explicitly composed:

```python
from vera_extract import convert

convert("manual.pdf", "manual.vera")
```

## Repository layout

```text
packages/
  vera-doc/
    src/vera/
      core/
      database.py
      document.py
      models.py
      collection.py
      corpus.py
  vera-extract/
    src/vera_extract/
      convert.py
      ingest/
        chunking.py
        parsers/pdf.py
        tessdata/
  vera-cli/
    src/vera_cli/
      commands.py
      evaluate.py
  vera-mcp/
    src/vera_mcp/
      server.py
  vera-app/
```

The root uv workspace links packages as editable dependencies. Published
packages use normal version constraints; source copying and Git submodules are
not dependency mechanisms.

## Format compatibility

New databases and conversions write VERA 0.2. `VeraDocument` remains a
read-oriented compatibility facade for the CLI, app, MCP adapter, and legacy
0.1 archives. New applications should prefer `VeraDatabase`.

The 0.1 document/page/block schema is documented in
[vera-spec-v0.1.md](vera-spec-v0.1.md). The chunk-oriented current format is
[vera-spec-v0.2.md](vera-spec-v0.2.md).

## Repository strategy

Keep the packages in one GitHub repository while schema, extraction, CLI, and
desktop changes commonly need atomic integration work. Separate repositories
only when ownership, release cadence, governance, or deployment constraints
actually diverge. Before a split, publish versioned wheels and test dependents
against both minimum and latest supported package versions.
