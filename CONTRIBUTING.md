# Contributing to VERA

Thank you for contributing. This document is the human-facing contributor
guide. Agents working in this repository should also read [AGENTS.md](AGENTS.md).

## Development setup

Python 3.10+, dependencies managed with [uv](https://docs.astral.sh/uv/):

```bash
uv sync --extra dev --extra ml --extra app --extra mcp --extra docling
```

The desktop app also needs Node.js 22+:

```bash
npm --prefix packages/vera-app install
```

## Checks

Run these before opening a pull request:

```bash
uv run ruff check packages tests benchmarks conftest.py
uv run ruff format --check packages tests benchmarks conftest.py
uv run mypy packages/vera-doc/src
uv run --extra dev pytest -q
npm run app:typecheck
npm --prefix packages/vera-app run test:unit
```

Retrieval quality is tracked with `vera eval` against the query sets in
[examples](examples). Do not regress the baselines in the README when search
behavior changes.

Windows packaged-sidecar release gate (optional locally; CI runs it on `v*`
tags):

```bash
uv sync --extra app --extra sidecar --extra docling --extra ml
npm --prefix packages/vera-app run build:sidecar
node packages/vera-app/scripts/verify-packaged-sidecar.cjs
```

`build:sidecar` vendors MiniLM and Docling layout/table snapshots from Hugging
Face into gitignored `packages/vera-app/build/` (about 380 MB extra on the
first run; later builds reuse the snapshot). If
`%APPDATA%\@vera\app\docling-artifacts` or `%APPDATA%\VERA\docling-artifacts`
already has a complete Heron ONNX + TableFormer accurate cache, the sidecar
build copies it instead of downloading again. Override the source with
`VERA_DOCLING_VENDOR_CACHE`.

## Formatting and blame

Python sources are formatted with Ruff. A one-time format pass lives in
`.git-blame-ignore-revs`. Enable it locally:

```bash
git config blame.ignoreRevsFile .git-blame-ignore-revs
```

Install git hooks (optional):

```bash
uv run pre-commit install
```

## Package layout

VERA is a uv workspace of independently installable packages. Dependencies
point inward at the storage engine:

```text
vera-ingest-pymupdf ─┐
vera-ingest-docling ─┤
vera-ingest ─────────┼──> vera-doc
vera-cli ────────────┤
vera-app ────────────┤
vera-mcp ────────────┘
vera-lab (dev only) ─┘
```

- Storage/search: `packages/vera-doc/src/vera_doc`
- Ingest core: `packages/vera-ingest/src/vera_ingest`
- Default PDF pipeline: `packages/vera-ingest-pymupdf/src/vera_ingest_pymupdf`
- Optional Docling pipeline: `packages/vera-ingest-docling/src/vera_ingest_docling`
- MCP: `packages/vera-mcp/src/vera_mcp`
- CLI: `packages/vera-cli/src/vera_cli`
- Ingest layout lab (dev): `packages/vera-lab/src/vera_lab`

The current format spec is [docs/vera-spec-v0.2.md](docs/vera-spec-v0.2.md) —
keep code and spec in sync. Details in
[docs/architecture.md](docs/architecture.md).

`vera-doc` must not import extraction, UI, MCP, or a source-file format.
`tests/test_package_boundaries.py` enforces that boundary. Package-specific
tests live in `packages/*/tests/`; shared PDF factories and CLI helpers live in
`tests/helpers/`. Cross-package contract tests stay in `tests/`.

## Documentation

Keep human and agent documentation current. Any user-visible feature change
must update the relevant [README](README.md), human guide under
[docs](https://dkylewillis.github.io/vera/), examples, portable
[agent skill](skills/vera/SKILL.md), and documentation-contract tests in the
same change. Changes to CLI commands or flags, JSON output, exit codes, MCP
tools, installation requirements, or retrieval behavior must also update the
relevant files under
[skills/vera/references](skills/vera/references). Do not merge a feature whose
public behavior is only documented in implementation code or tests.

See `.github/pull_request_template.md` for the PR checklist.
