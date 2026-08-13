# Using VERA as an AI agent

This file teaches AI coding agents how to use VERA to retrieve context from documents.

## What is an `.vera` file?

A single SQLite vector database containing ready-made chunks, JSON metadata,
pre-computed embeddings, and optional opaque attachments. Extraction may record
pages, headings, figures, and regions as metadata or attachments. You can search
it instantly — no parsing, chunking, embedding API calls, or retrieval service. See
[docs/vera-spec-v0.2.md](docs/vera-spec-v0.2.md) for the current format specification.

## Quick reference

All one-shot commands support `--json` for machine-readable output on stdout.
`vera mcp` is a long-running stdio server and does not accept `--json`.

```bash
# Search a document (hybrid = semantic + keyword, best default)
vera search manual.vera "stormwater detention requirements" --top-k 5 --json

# Search a folder of .vera files as one corpus (results include "file")
vera search ./library "stormwater detention requirements" --top-k 5 --json

# Search nested folders directly, or build a persistent local library index
vera search ./library "stormwater detention requirements" --recursive --json
vera index build ./library --recursive --json
vera index update ./library --json
vera index status ./library --json

# Include figure/table metadata near each result
vera search manual.vera "pipe sizing chart" --json --figures

# Include adjacent text context around each hit
vera search manual.vera "stormwater detention requirements" --json --context-chunks 1

# Keyword-only or semantic-only search
vera search manual.vera "section 4.2" --mode keyword --json
vera search manual.vera "how big should the pond be" --mode semantic --json

# Include highlight regions (page + bounding boxes) for visual grounding
vera search manual.vera "detention requirements" --json --regions

# Export the original source document (e.g. the PDF) back out
vera export manual.vera exported.pdf --json

# What's in this file?
vera inspect manual.vera --json

# Is this file well-formed? (exit code 0 = valid, 1 = invalid)
vera validate manual.vera --json

# Create an .vera from a PDF
vera convert manual.pdf manual.vera --json

# Batch-convert a nested PDF library beside its source files
vera convert ./proposals --recursive --json
```

Conversion selectively OCRs image-based low-text pages through the default
`vera-ingest-pymupdf` pipeline (PyMuPDF + Tesseract with bundled English data;
`--ocr auto|off|force`, `--ocr-language`, `--ocr-dpi` as compatibility aliases;
prefer repeatable `--pipeline-option KEY=VALUE` for provider-owned settings)
and publishes a validated temporary sibling atomically. PDFs with no searchable
chunks after OCR fail with an OCR-specific message. Directory conversion
skips an existing `.vera` only when it validates and its stored
`source_file_hash` matches the current PDF, and reports malformed archives
in `malformed_existing`. Python `convert()` / `batch_convert()` callers should
pass `parser` (default `pymupdf`), `pipeline_options`, and embedder settings
(`model` / `embedding_function` / `embedder_options`); legacy kwargs such as
`chunk_size`, `overlap`, `ocr_mode`, `ocr_language`, `ocr_dpi`, and
`ocr_download` are compatibility aliases forwarded only when explicitly
provided and the selected pipeline advertises them. Omitted aliases mean
the pipeline's own default.

### Search result shape (`--json`)

```json
{
  "query": "stormwater detention requirements",
  "mode": "hybrid",
  "results": [
    {
      "chunk_id": "chunk_0042",
      "score": 0.91,
      "page_start": 117,
      "page_end": 118,
      "heading_path": "Chapter 4 > 4.2 Detention Design",
      "source_filename": "manual.pdf",
      "document_id": "document_0001",
      "text": "..."
    }
  ]
}
```

Directory searches add `file` to each result and a top-level `index` status
object. They also add top-level `skipped_files` diagnostics for malformed
archives excluded from the search and `skipped_semantic_model_groups` for
indexed model groups omitted because the query embedder was unavailable or
dimension-incompatible. Result order is the rank; the CLI does not emit a
`rank` field.

## Rules for agents

1. **Always cite sources.** Every result includes `page_start`/`page_end` and
   `heading_path`. Quote them when answering from a document, e.g.
   *"(p. 117, Chapter 4 > 4.2 Detention Design)"*.
2. **Prefer `--mode hybrid`** (the default). Use `keyword` only for exact phrases,
   IDs, or section numbers; use `semantic` for paraphrased natural-language questions.
3. **Use `--figures`** when the question involves tables, charts, diagrams, or maps —
   results gain a `figures` array with captions and page locations.
4. **Use `--context-chunks N`** when an answer needs surrounding prose — results gain
  `before_chunks` and `after_chunks` arrays with citation-ready neighboring chunks.
5. **Use `--regions`** when a viewer needs to highlight where a chunk came from —
   results gain a `regions` array of
   `{block_id, page_number, bbox, page_width, page_height}` (bbox in page points,
   origin top-left).
6. **Check exit codes.** Parse stdout as JSON on exit 0. `validate`, `index status`,
   `eval`, and a failed `export` can also print a structured JSON report on exit 1;
   most missing-path/runtime errors instead write an unstructured traceback to stderr.
7. **Don't read the SQLite file directly** unless the CLI is unavailable — the schema
   is documented in the spec, but the CLI/MCP tools are the stable interface.

For the complete reusable workflow, load [skills/vera/SKILL.md](skills/vera/SKILL.md).
Its [CLI reference](skills/vera/references/cli-reference.md) documents every flag,
JSON shape, exit code, and filesystem side effect. See
[docs/agent-skills.md](docs/agent-skills.md) to install the skill in Hermes,
OpenClaw, Cursor, or another Agent Skills client.

## MCP server

VERA ships an MCP server (stdio) exposing the same capabilities as tools:

| Tool | Purpose |
|------|---------|
| `vera_search` | Hybrid/semantic/keyword search with optional figure metadata and highlight regions |
| `vera_corpus_search` | Search every .vera file in a directory as one corpus; results attributed per file |
| `vera_inspect` | Document metadata, page/chunk counts, embedding model |
| `vera_validate` | Integrity check |
| `vera_figures` | List figures/images with captions, optionally by page range |
| `vera_get_page` | Full text of a specific page |
| `vera_get_chunk_regions` | Page numbers + bounding boxes a chunk's text came from (visual grounding) |

Requires the integration package: `pip install "vera-cli[mcp]"` or `pip install vera-mcp`. Example VS Code config
(`.vscode/mcp.json`):

```json
{
  "servers": {
    "vera": {
      "command": "uv",
      "args": ["run", "--extra", "mcp", "vera", "mcp"]
    }
  }
}
```

## Working on this repository

Contributor setup, checks, and package layout live in
[CONTRIBUTING.md](CONTRIBUTING.md). Keep human and agent documentation current.
Any user-visible feature change must update the relevant [README](README.md),
human guide under [docs](https://dkylewillis.github.io/vera/), examples,
portable [agent skill](skills/vera/SKILL.md), and documentation-contract tests
in the same change. Changes to CLI commands or flags, JSON output, exit codes,
MCP tools, installation requirements, or retrieval behavior must also update
the relevant files under [skills/vera/references](skills/vera/references).
Do not merge a feature whose public behavior is only documented in
implementation code or tests.

## Cursor Cloud specific instructions

The startup update script already runs `uv sync --extra dev --extra ml --extra app --extra mcp`
and `npm --prefix packages/vera-app install`, so dependencies are ready. Notes below are
non-obvious caveats for this environment; standard commands live in the sections above,
[README.md](README.md), and [docs/desktop-app-getting-started.md](docs/desktop-app-getting-started.md).

- `uv` installs to `~/.local/bin`, which is not on `PATH` for non-interactive shells. It is
  added to `~/.bashrc` (so interactive shells work); otherwise invoke it as
  `~/.local/bin/uv` or `export PATH="$HOME/.local/bin:$PATH"`. The uv venv lives at
  `/workspace/.venv`.
- Standard checks: `uv run --extra dev python -m pytest -q` (or `npm test`) for Python,
  `npm run app:typecheck` and `npm --prefix packages/vera-app run test:unit` for the app.
- Desktop app on Linux: the root `npm run app:dev` script hardcodes `npm.cmd` and only works
  on Windows. On Linux run the app directly: `npm --prefix packages/vera-app run dev`. Electron
  spawns the Python sidecar as `python -m vera_app.sidecar`, so set
  `VERA_APP_PYTHON=/workspace/.venv/bin/python` (the venv Python has numpy/pymupdf/pdfplumber);
  otherwise the sidecar fails to import its deps. In the cloud VM also set `DISPLAY=:1` and
  `ELECTRON_DISABLE_SANDBOX=1`. The dbus/GLib warnings Electron prints in the container are
  harmless.
- The desktop app's "Ask"/chat feature requires configuring an external or local LLM provider
  (OpenAI/OpenRouter/Ollama/LM Studio) — there is no offline/extractive answer mode, so Ask is
  blocked without a provider/API key. For fully offline testing use the left-sidebar **Search**
  view (pure hybrid/semantic/keyword retrieval with grounded citations and highlights) or the
  **Convert PDF** view; both run entirely through the sidecar with no LLM.
- MCP server (optional): `uv run --extra mcp vera mcp` (long-running stdio; no `--json`).
- There are no PDFs in the repo; generate one with the `reportlab` dev dependency when you need
  a sample to `vera convert`.
