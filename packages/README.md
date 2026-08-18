# VERA Mono-Repo Packages

The repository contains independently installable packages with one-way
dependencies.

See [Choose a package](https://dkylewillis.github.io/vera/packages/) for
package-specific concepts, guides, examples, and reference documentation.

Published on PyPI:

| Package | Import / command | Role |
|---------|------------------|------|
| [`vera-doc`](https://pypi.org/project/vera-doc/) | `import vera_doc` | Storage and search |
| [`vera-ingest`](https://pypi.org/project/vera-ingest/) | `import vera_ingest` | Conversion registry and shared ingest types |
| [`vera-ingest-pymupdf`](https://pypi.org/project/vera-ingest-pymupdf/) | `import vera_ingest_pymupdf` | Default PyMuPDF PDF ingest pipeline |
| [`vera-ingest-docling`](https://pypi.org/project/vera-ingest-docling/) | `import vera_ingest_docling` | Optional Docling ingest pipeline |
| [`vera-cli`](https://pypi.org/project/vera-cli/) | `vera` | CLI and evaluation |
| [`vera-mcp`](https://pypi.org/project/vera-mcp/) | `vera mcp` | MCP adapter |

## `vera-doc`

Publishes `vera_doc`. Owns only storage and search:

- chunk-oriented `.vera` schema and validation;
- typed chunk, attachment, and query-result objects;
- transactional CRUD and metadata filtering;
- embedding storage/generation;
- keyword, semantic, hybrid, corpus, and library-index search.

It must not import conversion, ingestion, chunking, PDF/OCR, MCP, CLI,
desktop, or evaluation modules.

## `vera-ingest`

Publishes `vera_ingest` and depends on `vera-doc`. Owns the ingest-pipeline
registry, shared descriptors/types, conversion orchestration, reusable
chunking helpers, and ingest-produced viewer helpers. It emits ready-made
`ChunkRecord` objects and optional opaque attachments. PDF providers register
through `vera.ingest_pipelines`.

## `vera-ingest-pymupdf`

Default PDF pipeline plugin that depends on `vera-ingest`, PyMuPDF, and
pdfplumber. Registers the `pymupdf` ingest pipeline (selective Tesseract OCR
with bundled English language data). Pulled in by `vera-cli` and `vera-app`
so conversion works out of the box.

## `vera-ingest-docling`

Optional CLI/library plugin that depends on `vera-ingest` and Docling.
Registers the `docling` / `docling:hybrid` ingest pipeline. `vera-cli`
installs it through the `docling` extra. `vera-app` depends on it directly;
the packaged Windows sidecar freezes it as **Advanced layout (slower)**.

## `vera-cli`

Publishes `vera_cli` and the `vera` command. Depends on `vera-doc`,
`vera-ingest`, and `vera-ingest-pymupdf`. Owns argument parsing, output
contracts, exit codes, and retrieval evaluation. The optional `mcp` extra
adds `vera-mcp`.

## `vera-mcp`

Publishes `vera_mcp` and depends on `vera-doc` plus `vera-ingest` for viewer
helpers. It is the protocol adapter for agent tools and owns no storage or
retrieval implementation.

## `vera-app`

Owns the Electron/React desktop app and Python sidecar. Depends directly on
`vera-doc`, `vera-ingest`, `vera-ingest-pymupdf`, `vera-ingest-docling`, and
`sentence-transformers`; it does not use the CLI as a backend. The packaged
Windows installer freezes those converters plus MiniLM and Docling layout/table
snapshots.

## `vera-lab`

Contributor layout lab (workspace `dev` extra only). Depends on `vera-ingest`
and PyMuPDF. Writes a self-contained HTML report with block/chunk/figure
overlays and layout lint. Not published as part of the release path and not a
pipeline provider.

## Dependency direction

```text
vera-ingest-pymupdf ──> vera-ingest ─┐
vera-ingest-docling ──> vera-ingest ─┤
vera-cli ─────────────────────────────┼──> vera-doc
vera-app ─────────────────────────────┤
vera-mcp ─────────────────────────────┘
vera-lab (dev only) ──────────────────┘
```

The uv workspace provides editable development links. Released packages use
ordinary Python package versions. The root test suite is the cross-package
integration contract.
