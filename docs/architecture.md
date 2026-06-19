# VERA Architecture and Refactor Plan

## Purpose

This note defines the target project boundaries for VERA after the package rename to `vera`. The goal is to let the project grow into separate document, CLI, and app surfaces while keeping behavior stable.

The first refactor should be intentionally boring: no schema changes, no search behavior changes, and no CLI output changes. The work should clarify ownership and module boundaries while preserving the existing public API.

## Current Shape

The current package, `vera`, contains several responsibilities in one namespace:

- `.vera` schema creation and format constants
- document opening, inspection, validation, search, context chunks, figures, and visual grounding regions
- PDF conversion, parsing, chunking, embedding, and writing
- corpus search over multiple `.vera` files
- CLI command parsing and output formatting
- retrieval evaluation utilities
- MCP server integration
- Streamlit workbench launcher

## Target Product Boundaries

### vera-doc

`vera-doc` is the core document and retrieval engine. It owns behavior that must be consistent across the CLI, app, MCP server, tests, and third-party consumers.

Responsibilities:

- `.vera` schema and format constants
- `.vera` reader/writer APIs
- document inspection and validation
- keyword, semantic, hybrid, and corpus search
- context chunks and citation-ready search result models
- chunking and chunk provenance
- embedding interfaces and built-in embedders
- PDF parser adapters and conversion pipeline
- assets, figures, captions, source-document access, and visual grounding regions
- public Python API contracts

Non-responsibilities:

- terminal argument parsing
- human-oriented CLI output formatting
- sessions, prompts, LLM calls, or user workflows
- UI state or source viewer presentation

### vera-cli

`vera-cli` is a thin command-line interface over `vera-doc`.

Responsibilities:

- command registration and argument parsing
- text and JSON output formatting
- process exit codes
- command-level error handling and messages
- shell-friendly workflows for convert, inspect, validate, search, export, eval, mcp, and workbench launch

Non-responsibilities:

- retrieval business logic
- schema or validation rules
- chunking, embedding, parsing, or search ranking
- app sessions or LLM orchestration

### vera-app

`vera-app` is the user-facing application layer. It should call `vera-doc` directly rather than shelling out to `vera-cli`.

Responsibilities:

- source document viewer and visual grounding
- user prompt input and prompt history
- sessions and saved research state
- instruction layering and response configuration
- LLM provider integrations
- external tool registry and tool-use policies
- answer rendering, citations, and evidence views
- app-specific auth, config, telemetry, and audit workflows

Non-responsibilities:

- low-level `.vera` schema behavior
- core search algorithm correctness
- CLI output compatibility

## Dependency Direction

Dependencies should move in one direction:

```text
vera-cli  -> vera-doc
vera-app  -> vera-doc
vera-mcp  -> vera-doc
```

`vera-doc` should not import from `vera-cli` or `vera-app`.

`vera-app` should not depend on `vera-cli` for normal operation. CLI commands are a user interface, not a backend API.

## Phase 1 Internal Structure

The current internal structure moves implementation code toward separable layers while keeping the package import path stable:

```text
src/vera/
  core/
    access.py
    embeddings.py
    figures.py
    inspection.py
    schema.py
    search.py
    validation.py
  ingest/
    chunking.py
    parsers/
      pdf.py
  cli/
    main.py
    commands.py
  integrations/
    mcp_server.py
```

During active development, internal tests and code should import implementation helpers from their owning layer instead of through compatibility shims:

```python
from vera import convert, VeraDocument
from vera.convert import convert
from vera.document import VeraDocument, SearchResult
from vera.ingest import build_chunks_from_blocks, chunk_pages
from vera.cli import main, build_parser, str_to_bool
from vera.integrations.mcp_server import build_server
```

## Future Package Boundary Extraction

After internal module boundaries settle, keep VERA as a mono-repo and move to a multi-package layout when package-level release boundaries are useful:

```text
packages/
  vera-doc/
  vera-cli/
  vera-app/
```

This should be the default next architectural step. A mono-repo keeps shared tests, examples, docs, schema changes, and cross-package refactors easy while still giving `vera-doc`, `vera-cli`, and `vera-app` clean package boundaries.

At that point, `vera-cli` and `vera-app` should depend on `vera-doc` through normal package dependencies. The root repo should own integration tests that prove the packages work together.

See [packages/README.md](../packages/README.md) for the package ownership rules and extraction criteria.

Separate repositories should wait until there is a clear reason, such as different owners, incompatible release cadences, governance requirements, or deployment constraints.

## Public API To Preserve

```python
from vera import convert, VeraDocument

convert("input.pdf", "output.vera")

doc = VeraDocument.open("output.vera")
try:
    info = doc.inspect()
    report = doc.validate()
    results = doc.search("query", mode="hybrid", top_k=5, context_chunks=1)
    figures = doc.figures_for(results[0]) if results else []
    regions = doc.regions_for(results[0]) if results else []
finally:
    doc.close()
```

CLI behavior should also remain stable:

```bash
vera convert input.pdf output.vera
vera inspect output.vera
vera validate output.vera
vera search output.vera "query" --mode hybrid --top-k 5
vera export output.vera
vera eval output.vera queries.json --mode all
vera mcp
vera workbench
```

For CLI compatibility, preserve JSON output shapes and exit-code behavior unless a deliberate breaking change is documented.

## Baseline

Use the project virtual environment for tests:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Baseline after syncing to `origin/main` and reapplying the internal refactor on 2026-06-18:

```text
140 passed
```

## Refactor Guardrails

- Do not change the `.vera` schema as part of structure-only refactors.
- Do not change search ranking behavior unless the change is explicit and evaluated.
- Do not change chunking behavior during module moves.
- Do not change CLI output formats during module moves.
- Do not change public import paths without compatibility shims.
- Do not introduce app/LLM behavior into core document modules.
- Run tests after each small move.

## Success Criteria

The structure is successful when:

- the full test suite passes through the project virtual environment
- existing Python imports continue to work
- existing CLI commands continue to work
- docs describe the new boundaries clearly
- `vera-doc` responsibilities are separable from CLI and app concerns
- future `vera-app` work can call document APIs directly without relying on CLI subprocesses
