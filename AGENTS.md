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

# List stored figures, or write PNGs an agent can attach
vera figures manual.vera --json
vera figures manual.vera --out-dir ./figures --json

# What's in this file?
vera inspect manual.vera --json

# Is this file well-formed? (exit code 0 = valid, 1 = invalid)
vera validate manual.vera --json

# Create an .vera from a PDF or Markdown file
vera convert manual.pdf manual.vera --json
vera convert notes.md notes.vera --json

# Docling (optional CLI extra: vera-cli[docling] or --extra docling; not in the 0.3.0 desktop app)
vera convert scan.pdf scan.vera --parser docling --json
vera convert scan.pdf scan.vera --parser docling --pipeline-option pdf_backend=pypdfium2 --json

# Provider-owned embedder options (hashing dimension; OpenAI batch_size)
vera convert manual.pdf --model hashing --embedder-option dimension=256 --json
vera convert manual.pdf --model openai:text-embedding-3-small --json

# Batch-convert a nested PDF and Markdown library beside its source files
vera convert ./proposals --recursive --json

# List or fetch curated Tesseract OCR language data (non-English)
vera ocr-languages list --json
vera ocr-languages download fra --json
```

Conversion selectively OCRs image-based low-text pages through the default
`vera-ingest-pymupdf` pipeline (PyMuPDF + Tesseract with bundled English data;
`--ocr auto|off|force`, `--ocr-language`, `--ocr-dpi` as compatibility aliases;
prefer repeatable `--pipeline-option KEY=VALUE` for provider-owned settings)
and publishes a validated temporary sibling atomically. PDFs with no searchable
chunks after OCR fail with an OCR-specific message. Markdown files with no
searchable text fail with a generic empty-file message. Directory conversion
skips an existing `.vera` only when it validates and its stored
`source_file_hash` matches the current source file, and reports malformed archives
in `malformed_existing`. Python `convert()` / `batch_convert()` callers should
pass `parser` (omitted: choose from the file extension), `pipeline_options`, and embedder settings
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
3. **Use `--figures`** when the question involves charts, diagrams, maps, or
   captions — results gain a `figures` array with `asset_id`, captions, and page
   locations. To **see** a stored raster, run `vera figures FILE --out-dir DIR`
   (or MCP `vera_get_figure`). Tables are usually markdown in chunk text, not
   figure attachments. Missing `asset_id` values mean no stored raster (vector
   art or decorative marks), not that you should crop the PDF.
4. **Use `--context-chunks N`** when an answer needs surrounding prose — results gain
  `before_chunks` and `after_chunks` arrays with citation-ready neighboring chunks.
5. **Use `--regions`** when a viewer needs to highlight where a chunk came from —
   results gain a `regions` array. PDF hits include
   `{kind, block_id, page_number, bbox, page_width, page_height}` (bbox in page points,
   origin top-left). Markdown hits use `{kind: "text_span", start, end}` line/column
   locators instead of page bounding boxes.
6. **Check exit codes.** Parse stdout as JSON on exit 0. `validate`, `index status`,
   `eval`, a failed `export`, a failed `figures`, and a failed `convert` can also print a structured JSON
   report on exit 1; `convert --json` uses the same `{ok, error}` object on exit 2
   for an unknown `--parser` / `--model`. Most other missing-path/runtime errors
   instead write an unstructured traceback to stderr.
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
| `vera_get_figure` | Fetch one stored figure as native image content plus citation metadata |
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
The desktop sidecar lives in
[packages/vera-app/src/vera_app](packages/vera-app/src/vera_app).
Do not merge a feature whose public behavior is only documented in
implementation code or tests.

## Cursor Cloud specific instructions

The startup update script already runs `uv sync --extra dev --extra ml --extra app --extra mcp --extra docling --extra onnx`
and `npm --prefix packages/vera-app install`, so dependencies are ready. Notes below are
non-obvious caveats for this environment; standard commands live in the sections above,
[README.md](README.md), and [docs/desktop-app-getting-started.md](docs/desktop-app-getting-started.md).

- `uv` installs to `~/.local/bin`, which is not on `PATH` for non-interactive shells. It is
  added to `~/.bashrc` (so interactive shells work); otherwise invoke it as
  `~/.local/bin/uv` or `export PATH="$HOME/.local/bin:$PATH"`. The uv venv lives at
  `/workspace/.venv`.
- Standard checks: `uv run --extra dev python -m pytest -q` (or `npm test`) for Python,
  `npm run app:typecheck` and `npm --prefix packages/vera-app run test:unit` for the app.
- Desktop app: `npm run app:dev` works on Linux, macOS, and Windows. It vendors
  the MiniLM ONNX graph into `packages/vera-app/build/minilm` before Electron
  starts. Electron
  spawns the Python sidecar as `python -m vera_app.sidecar`, so set
  `VERA_APP_PYTHON=/workspace/.venv/bin/python` (the venv Python has numpy/pymupdf/pdfplumber);
  otherwise the sidecar fails to import its deps. In the cloud VM also set `DISPLAY=:1` and
  `ELECTRON_DISABLE_SANDBOX=1`. The dbus/GLib warnings Electron prints in the container are
  harmless.
- The desktop app's "Ask"/chat feature requires configuring an external or local LLM provider
  (OpenAI/OpenRouter/Ollama/LM Studio) — there is no offline/extractive answer mode, so Ask is
  blocked without a provider/API key. For fully offline testing use the left-sidebar **Search**
  view (pure hybrid/semantic/keyword retrieval with grounded citations and highlights) or the
  **Convert** view. Convert lists PyMuPDF (PDF) and the bundled `markdown`
  pipeline. OpenAI embeddings are
  bundled (`openai:text-embedding-3-small` / `-large`); hashing remains the
  default. Save `OPENAI_API_KEY` under **File > Settings → Embeddings** (or
  export it for CLI convert). Archives converted with OpenAI are not portable
  for semantic search. Docling is a CLI extra
  (`uv sync --extra docling`; `vera convert --parser docling`), not a desktop
  pipeline in 0.3.0. The packaged
  Windows sidecar freezes ONNX Runtime and vendors a VERA-exported
  `all-MiniLM-L6-v2` graph (`VERA_ONNX_MINILM_HOME` /
  `VERA_SENTENCE_TRANSFORMERS_HOME`);
  packaged `HF_HOME` stays under userData. `app:dev` leaves `HF_HOME` unset
  and vendors MiniLM into `packages/vera-app/build/minilm` before launch. Convert
  timing lines (`elapsed_ms`) go to
  sidecar stderr and are teed to `userData/logs/sidecar.log`; open it from
  **File > Open convert log...**. Ask is
  blocked without a provider/API key.
- MCP server (optional): `uv run --extra mcp vera mcp` (long-running stdio; no `--json`).
- There are no PDFs in the repo; generate one with the `reportlab` dev dependency when you need
  a sample to `vera convert`.
