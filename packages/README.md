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
| [`vera-embed-openai`](https://pypi.org/project/vera-embed-openai/) | `import vera_embed_openai` | Official OpenAI embeddings plugin |
| [`vera`](https://pypi.org/project/vera/) | `vera` / `import vera_cli` | CLI and evaluation |
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
`ChunkRecord` objects and optional opaque attachments. PDF and Markdown
providers register through `vera.ingest_pipelines` (Markdown is bundled in
this package; PyMuPDF and Docling are separate plugins).

## `vera-ingest-pymupdf`

Default PDF pipeline plugin that depends on `vera-ingest`, PyMuPDF, and
pdfplumber. Registers the `pymupdf` ingest pipeline (selective Tesseract OCR
with bundled English language data). Pulled in by `vera` and `vera-app`
so conversion works out of the box.

## `vera-ingest-docling`

Optional CLI/library plugin that depends on `vera-ingest` and Docling.
Registers the `docling` / `docling:hybrid` ingest pipeline. `vera`
installs it through the `docling` extra. It is not bundled into packaged desktop releases. The Convert view lists it only when a separate Python environment chosen under **Settings → Plugins** has it; `vera-ingest` then runs each conversion in that environment (`VERA_PIPELINE_PYTHON`).

## `vera-embed-openai`

Official OpenAI embeddings plugin. Registers the `openai` provider with
stdlib HTTPS (no OpenAI SDK). Pulled in by `vera` and `vera-app` so
hosted conversion works out of the box. Archives converted with it are not
portable for semantic search.

## `vera`

Publishes `vera_cli` and the `vera` command (`vera` on PyPI; source in
`packages/vera-cli`). Depends on `vera-doc`, `vera-ingest`,
`vera-ingest-pymupdf`, and `vera-embed-openai`. Owns argument parsing, output
contracts, exit codes, and retrieval evaluation. The optional `mcp` extra
adds `vera-mcp`. `vera-cli` on PyPI is a compatibility alias that depends on
`vera` (source in `packages/vera-cli-compat`).

## `vera-mcp`

Publishes `vera_mcp` and depends on `vera-doc` plus `vera-ingest` for viewer
helpers. It is the protocol adapter for agent tools and owns no storage or
retrieval implementation.

## `vera-app`

Owns the Electron/React desktop app and Python sidecar. Depends directly on
`vera-doc`, `vera-ingest`, `vera-ingest-pymupdf`, ONNX Runtime,
`tokenizers`, and `vera-embed-openai`; it does not use the CLI as a backend. The packaged
Windows installer freezes PyMuPDF, OpenAI embeddings, plus a VERA-exported MiniLM ONNX graph
(not Torch). The Docling CLI extra is
not bundled in the installer.

## `vera-lab`

Contributor layout lab (workspace `dev` extra only). Depends on `vera-ingest`
and PyMuPDF. Writes a self-contained HTML report with block/chunk/figure
overlays and layout lint. Not published as part of the release path and not a
pipeline provider.

## `vera-ingest-plans`

Optional workspace plugin (`plans` extra; not published to PyPI and not in the
desktop installer). Depends on `vera-ingest` and `vera-ingest-pymupdf` and
registers the `plans` ingest pipeline for construction drawing sets
(drawn-text OCR, detail titles in chunk text). Its wheel is pure Python, so the
desktop app can install it from **Settings → Plugins**.

## Dependency direction

```text
vera-ingest-pymupdf ──> vera-ingest ─┐
vera-ingest-docling ──> vera-ingest ─┤
vera-ingest-plans ──> vera-ingest-pymupdf
vera-embed-openai ───────────────────┤
vera ─────────────────────────────────┼──> vera-doc
vera-app ─────────────────────────────┤
vera-mcp ─────────────────────────────┘
vera-lab (dev only) ──────────────────┘
```

The uv workspace provides editable development links. Released packages use
ordinary Python package versions. The root test suite is the cross-package
integration contract.
