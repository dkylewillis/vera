# Concepts

This page explains the core ideas behind VERA at a level useful for working with
the public Python API and CLI.

## `.vera` archives

A `.vera` file is a single SQLite database containing:

- **Chunks** — searchable text segments with JSON metadata (page numbers,
  heading paths, layout regions, and caller-defined fields).
- **Embeddings** — pre-computed vectors for semantic search, stored alongside
  the chunk they represent.
- **Keyword index** — an FTS5 full-text index for exact-term and phrase
  matching.
- **Attachments** — optional opaque bytes (original PDFs, figure images,
  viewer payloads) linked to chunks by reference.

Archives are validated at creation time and can be inspected or re-validated at
any point with `vera inspect` / `vera validate` or the Python equivalents.

## Chunks and records

Applications that already have final text use **`ChunkRecord`** objects. VERA
does not parse or chunk source files inside `vera-doc`; that work lives in
`vera-extract`.

Each record has:

| Field | Purpose |
|-------|---------|
| `id` | Stable identifier within the archive |
| `text` | Searchable content |
| `metadata` | JSON-compatible citation and filter fields |
| `vector` | Optional pre-computed embedding (embedded automatically when omitted) |
| `attachments` | Optional links to stored binary attachments |

## Search modes

| Mode | Best for |
|------|----------|
| `hybrid` | General questions and regulatory prose (default) |
| `keyword` | Section numbers, IDs, and exact phrases |
| `semantic` | Paraphrased natural-language questions |

Hybrid search fuses semantic and keyword rankings. Results include relevance
scores plus citation metadata — use the metadata as evidence, not the score
alone.

## Read vs write access

**`VeraDatabase`** is the primary CRUD and search API. Open archives in
read-only mode (the default) for search and inspection; use write mode for
mutations.

**`VeraDocument`** is a read-oriented compatibility facade used by the CLI,
desktop app, and MCP adapter. It adds figure listing, page access, highlight
regions, and source export on top of search. New applications performing CRUD
should prefer `VeraDatabase`.

## Document libraries

Searching many `.vera` files in a folder uses **`VeraCorpus`**. For large
libraries, build a persistent **library index** (`.vera-index/`) with
`build_library_index()` or `vera index build`. The index is derived and
rebuildable; the `.vera` files remain the source of truth.

## Package responsibilities

```text
vera-doc       Storage, search, corpus, library indexes
vera-extract   PDF parsing, OCR, chunking, conversion to .vera
vera-cli       Command-line interface (vera convert, search, index, …)
vera-mcp       Model Context Protocol server for AI agents
vera-app       Desktop app Python sidecar (Electron)
```

Conversion composes `vera-extract` with `vera-doc`. Search and indexing use
`vera-doc` directly.

## Related reading

- [Format specification (0.2)](../vera-spec-v0.2.md) — on-disk schema details.
- [Python API guide](../python-api.md) — narrative API walkthrough.
- [Collection index design](../collection-index.md) — how library indexes work.
- [API reference](../reference/database.md) — generated Python API docs.
