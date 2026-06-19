# VERA Mono-Repo Packages

This directory is reserved for the future multi-package mono-repo layout.

The current package remains `src/vera` until the internal module boundaries are stable enough to extract package-level distributions without changing behavior.

## Planned Packages

### vera-doc

Core document and retrieval engine.

Owns:

- `.vera` schema, validation, readers, and writers
- conversion, parsing, chunking, embeddings, and assets
- document and corpus search
- citation metadata, context chunks, figures, and visual grounding regions
- public Python APIs used by the CLI, app, MCP integration, and third-party consumers

### vera-cli

Command-line interface over `vera-doc`.

Owns:

- argument parsing
- text and JSON output formatting
- process exit codes
- terminal-oriented command behavior

`vera-cli` should not own retrieval, validation, schema, chunking, or parsing logic.

### vera-app

User-facing application layer over `vera-doc`.

Owns:

- source document viewer and visual grounding UX
- sessions, prompts, instructions, and response configuration
- LLM provider integrations
- external tool connections and tool-use policies
- app-specific auth, telemetry, and audit workflows

`vera-app` should call `vera-doc` directly and should not shell out to `vera-cli` for normal operation.

## Dependency Direction

```text
vera-cli  -> vera-doc
vera-app  -> vera-doc
vera-mcp  -> vera-doc
```

The core document package must not import from CLI or app packages.

## Extraction Criteria

Create actual package directories here only when at least one of these is true:

- the root `src/vera` package boundaries are stable
- `vera-cli` needs independent release or dependency metadata
- `vera-app` needs its own runtime stack
- downstream consumers need a smaller core dependency than the full repo package

Until then, keep the internal structure under `src/vera` and use the root test suite as the source of truth.
