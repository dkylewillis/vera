# VERA Mono-Repo Packages

The repository contains independently installable packages with one-way
dependencies.

See [Choose a package](https://dkylewillis.github.io/vera/packages/) for
package-specific concepts, guides, examples, and reference documentation.

## `vera-doc`

Publishes `vera`. Owns only storage and search:

- chunk-oriented `.vera` schema and validation;
- typed chunk, attachment, and query-result objects;
- transactional CRUD and metadata filtering;
- embedding storage/generation;
- keyword, semantic, hybrid, corpus, and library-index search.

It must not import conversion, extraction, chunking, PDF/OCR, MCP, CLI,
desktop, or evaluation modules.

## `vera-extract`

Publishes `vera_extract` and depends on `vera-doc`. Owns PDF parsing, OCR,
tables, heading detection, chunking, conversion, and extraction provenance.
It emits ready-made `ChunkRecord` objects and optional opaque attachments.

## `vera-cli`

Publishes `vera_cli` and the `vera` command. Depends on `vera-doc` and
`vera-extract`. Owns argument parsing, output contracts, exit codes, and
retrieval evaluation. The optional `mcp` extra adds `vera-mcp`.

## `vera-mcp`

Publishes `vera_mcp` and depends on `vera-doc`. It is the protocol adapter for
agent tools and owns no storage or retrieval implementation.

## `vera-app`

Owns the Electron/React desktop app and Python sidecar. Depends directly on
`vera-doc` and `vera-extract`; it does not use the CLI as a backend.

## Dependency direction

```text
vera-extract ─┐
vera-cli ─────┼──> vera-doc
vera-app ─────┤
vera-mcp ─────┘
```

The uv workspace provides editable development links. Released packages use
ordinary Python package versions. The root test suite is the cross-package
integration contract.
