# VERA Architecture

## Package boundaries

VERA is a mono-repo of independently installable packages. Dependencies move
inward toward the storage and search engine:

```text
vera-ingest ─┐
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

### `vera-ingest`

`vera-ingest` publishes `vera_ingest`. It owns all source interpretation:

- PDF parsing and table extraction, plus optional ingest pipeline plugins;
- selective OCR and bundled Tesseract data;
- heading detection and chunk construction;
- mapping pages, regions, figures, and provenance to chunk metadata;
- optional source/image/viewer attachments;
- reader helpers for pages, figures, regions, and source export;
- single-file and batch conversion workflows.

It emits final `ChunkRecord` objects and writes them through `VeraDocument`.
`vera-doc` never imports `vera_ingest`.

### `vera-cli`

`vera-cli` publishes the `vera` console script and `vera_cli` module. It owns
argument parsing, text/JSON formatting, exit codes, and retrieval evaluation.
Conversion commands compose `vera-ingest` with `vera-doc`.

### `vera-mcp`

`vera-mcp` publishes `vera_mcp` and the `vera-mcp` console script. It is a
thin MCP adapter over `vera-doc` search/storage APIs and `vera-ingest.viewer`
helpers. The optional `vera-cli[mcp]` extra installs it for `vera mcp`.

### `vera-app`

`vera-app` owns the Electron/React desktop application, Python sidecar, LLM
providers, sessions, and application state. Packaged conversions keep the
frozen sidecar for search, indexing, Ask, and the bundled `pymupdf` pipeline.
Optional ingest plugins run in a shipped `vera_plugin_host` worker launched
with a user-selected Python interpreter. The app depends on both `vera-doc`
and `vera-ingest` (including viewer helpers), not on `vera-cli`.

## Core Python API

Applications that already have chunks need only `vera-doc`:

```python
from vera import ChunkRecord, VeraDocument

with VeraDocument.create("knowledge.vera") as document:
    document.add(
        [
            ChunkRecord(
                id="requirements-1",
                text="The minimum pipe diameter is 12 inches.",
                metadata={"source": "manual.pdf", "page": 42},
            )
        ]
    )

with VeraDocument.open("knowledge.vera") as document:
    results = document.search(text="minimum pipe size", top_k=5)
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
from vera_ingest import convert

convert("manual.pdf", "manual.vera")
```

## Repository layout

```text
packages/
  vera-doc/
    src/vera/
      core/
      document.py
      document.py
      models.py
      collection.py
      corpus.py
  vera-ingest/
    src/vera_ingest/
      convert.py
      pipeline.py
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
    src/vera_app/
      sidecar.py
    src/vera_plugin_host/
      worker.py
    electron/
      main.ts
```

The root uv workspace links packages as editable dependencies. Published
packages use normal version constraints; source copying and Git submodules are
not dependency mechanisms.

## Format compatibility

New archives and conversions write VERA 0.2 only. The chunk-oriented current
format is documented in [vera-spec-v0.2.md](vera-spec-v0.2.md). The older
0.1 document/page/block schema remains in
[vera-spec-v0.1.md](vera-spec-v0.1.md) for historical reference and is no
longer read by `vera-doc`.

## Repository strategy

Keep the packages in one GitHub repository while schema, extraction, CLI, and
desktop changes commonly need atomic integration work. Separate repositories
only when ownership, release cadence, governance, or deployment constraints
actually diverge. Before a split, publish versioned wheels and test dependents
against both minimum and latest supported package versions.
