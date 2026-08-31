# Changelog

Notable changes to VERA software, CLI, and Python APIs.

**0.3.x versions the packages, CLI, and desktop app.** The `.vera` archive
format remains **0.2**. Existing archives are compatible; you do not need to
reconvert files created with 0.2 tooling in order to search or inspect them.

## [Unreleased]

### Added

- `vera get FILE CHUNK_ID` fetches one stored chunk by id as citation-ready
  JSON (`ok`, locator fields, `chunk_id`, `text`, and the same citation keys
  as a search hit, without `score`). `--figures` and `--regions` match search
  enrichment. An unknown or whitespace-only id exits 1 with
  `{"ok": false, "error": "chunk not found: ..."}`. MCP `vera_get_chunk` returns
  the same object. Shared `vera_ingest.viewer.chunk_payload()` flattens a
  `ChunkRecord`; `result_payload()` layers retrieval scores on top.

- Markdown ingest: `vera convert notes.md` (and directory discovery of `.md` /
  `.markdown`) uses a bundled `markdown` pipeline in `vera-ingest`. Convert
  selects a pipeline from the file extension when `--parser` is omitted.
  Explicit `--parser pymupdf` on a Markdown file fails instead of silently
  switching. Search citations use heading paths and `text_span` locators;
  the original Markdown is stored for export and desktop preview. Explorer,
  Convert, and Reconvert treat PDFs and Markdown as convertible sources.

## [0.3.1] — 2026-08-24

### Added

- `vera figures FILE` lists stored figure metadata (captions, pages, bboxes,
  `asset_id`) and, with `--out-dir`, writes `{asset_id}.{ext}` image files and
  adds `path` to JSON. Missing or non-figure `--asset-id` values exit 1 with
  `{"ok": false, "error": "..."}`.
- MCP `vera_get_figure(file, asset_id)` returns native image content plus
  citation metadata. `vera_figures` and `vera_search(include_figures=...)`
  stay metadata-only.
- `vera_ingest.export_figures()` writes figure attachments under a directory
  with the same path-safety rules as `export_source_document()`.
- Official `vera-embed-openai` plugin: stdlib HTTPS client for
  `text-embedding-3-small`, `text-embedding-3-large`, and
  `text-embedding-ada-002`. `vera-cli` and `vera-app` depend on it the same
  way they depend on PyMuPDF; the frozen sidecar registers it via
  `ensure_registered()`. See [docs/packages/vera-embed-openai.md](docs/packages/vera-embed-openai.md).
- Desktop **Settings → Embeddings** stores `OPENAI_API_KEY` through the
  existing encrypted env-secret IPC. Convert presets include the two
  `text-embedding-3-*` models; hashing remains the default.
- Archives converted with a hosted embedder are not portable for semantic
  search: the recipient needs their own `OPENAI_API_KEY`. Keyword search
  still works.

### Changed

- `vera-mcp` depends on `mcp>=1.0,<2`. MCP Python SDK 2.x removed
  `mcp.server.fastmcp`; a fresh unbounded install could not start `vera mcp`.
  Install `vera-cli[mcp]`, not a bare `mcp` 2.x package.

- Packaged MiniLM uses ONNX Runtime instead of PyTorch / Sentence Transformers.
  Archive identity stays `sentence-transformers/all-MiniLM-L6-v2`. The installer
  vendors a VERA-exported fp32 graph (SHA256-pinned via `export_minilm_onnx.py`
  and `compare_minilm_onnx.py`). `app:dev` vendors the ONNX
  snapshot before launch. Sidecar
  freeze `--exclude-module`s Torch / Sentence Transformers even when the
  project venv has the `ml` extra; MiniLM export in release CI uses a throwaway
  venv.

- MiniLM selects its runtime by what is actually available: ONNX Runtime when a
  VERA-exported graph is present, Sentence Transformers otherwise. Installing
  the `onnx` extra no longer makes MiniLM fail when no graph is vendored, so
  `pip install "vera-doc[ml]"` is enough for MiniLM on the CLI and a checkout
  synced with `--extra onnx --extra ml` works without
  `VERA_ONNX_MINILM_HOME`. The packaged app and `app:dev` are unaffected —
  both vendor a graph and still never load Sentence Transformers.

### Fixed

- `vera convert --json` and `vera search --json` report OpenAI embedder
  failures (missing `OPENAI_API_KEY`, HTTP errors) as
  `{"ok": false, "error": "..."}` instead of an uncaught traceback.

## [0.3.0] — 2026-08

### Added

- Pluggable ingest pipelines through the `vera.ingest_pipelines` entry-point
  group and `register_ingest_pipeline()`. Select a pipeline with
  `vera convert --parser provider[:variant]` or `convert(..., parser=...)`.
- Provider-owned ingest settings via repeatable
  `vera convert --pipeline-option KEY=VALUE` and `pipeline_options=` on
  `IngestRequest`. Legacy flags (`--chunk-size`, `--overlap`, `--ocr`,
  `--ocr-language`, `--ocr-dpi`) remain compatibility aliases; descriptor
  fields and OCR engine control which aliases are forwarded. Tesseract
  `--ocr-language` (`eng`) is not forwarded to Docling/RapidOCR, which
  keeps its own default `en`.
- Pipeline descriptors for discovery and schema-driven UI:
  `describe_ingest_pipelines`, typed pipeline options, and the desktop
  Convert view's `PipelineConfigForm` / **Advanced pipeline options**.
- Official Docling converter (`vera-ingest-docling`) registering
  `docling` / `docling:hybrid`, with HybridChunker, RapidOCR, first-run
  model-download notes, and `pdf_backend` recovery on page-level memory
  errors (per-page retry, whole-document `pypdfium2`, then page-batch
  `pypdfium2`). RapidOCR uses the ONNX weights shipped with `docling[rapidocr]`
  even when `DOCLING_ARTIFACTS_PATH` only holds layout models. Install it with
  `vera-cli[docling]` or `uv sync --extra docling`. The 0.3.0 desktop app does
  not list or freeze this pipeline (Convert is PyMuPDF-only).
- Pluggable embedding providers through the `vera.embedders` entry-point
  group and `register_embedder()`. Model specs use `provider:model-id`
  (existing aliases still work).
- Provider-owned embedder settings via `--embedder-option KEY=VALUE` /
  `embedder_options=`, advertised through `EmbedderOptions` metadata and
  `describe_embedding_providers`.
- Embedder capability helpers: `vera.embedder_models` /
  `list_embedding_models`, `preflight_embedder`, and
  `capabilities.credential_env` (secrets stay in environment variables, not
  Options).
- Desktop Convert view: persist the selected embedding model separately from
  Chat; show installed provider suggestions; hashing and MiniLM presets.
- Packaged desktop app: one frozen sidecar with PyMuPDF, hashing, and
  Sentence Transformers. MiniLM (`all-MiniLM-L6-v2`) weights ship in the
  installer, so Local semantic conversion does not download those files on
  first use. Docling is not part of the 0.3.0 installer or Convert view;
  use `vera-cli[docling]` for that pipeline. There is no Settings → Python
  plugins page and no `vera_plugin_host`. Convert drives `EmbedderConfigForm`
  from descriptors, persists `embedder_configs`, and gates conversion on
  `preflight_embedder`. Search reports `skipped_semantic_model_groups` when a
  query embedder is unavailable. Hosted embedding providers were not part of
  0.3.0; OpenAI now ships as `vera-embed-openai` (see 0.3.1).
- Desktop convert timing log: sidecar stderr (including `elapsed_ms` convert
  steps) is teed to `userData/logs/sidecar.log` in both `app:dev`
  and packaged VERA. **File > Open convert log...**, Convert **Open log**, and
  **Settings → Diagnostics** open it. CLI `vera convert` still prints the same
  timing on stderr only.

- Typed `Citation` on search hits (`result.citation`) plus configurable hybrid
  `semantic_weight` / `keyword_weight` on `VeraDocument.search()`.
- Shared `vera_ingest.viewer.result_payload()` serializer for CLI, MCP, and
  desktop search JSON.
- Vectorized semantic scoring, batched attachment loads, and FTS writes that
  align `chunks_fts.rowid` with `chunks.rowid` (format 0.2 compatible; legacy
  archives fall back to deleting by `chunk_id` and to appending when another
  chunk already occupies the matching FTS rowid).
- `VeraDocument.iter_raw_chunks()` / `format_metadata()` for library indexing
  without private `VeraDocument` access.
- `vera ocr-languages list` and `vera ocr-languages download` for Tesseract
  language data used by the PyMuPDF pipeline (English is bundled; other
  languages are fetched into a local cache).
- `vera-lab` contributor layout lab (workspace `dev` extra only; not
  published to PyPI).

### Changed

- `EmbedderOptions` and `PipelineOptions` `from_mapping` reject integers
  outside advertised `minimum`/`maximum` (hashing `dimension` 8–4096,
  pipeline `chunk_size` 100–3000).
- Conversion writes a validated temporary sibling and publishes atomically.
  Empty (no searchable chunks) conversions fail with an OCR-oriented message.
  `vera convert --json` prints `{"ok": false, "error": "..."}` for those
  failures, a missing input path (exit 1), and an unknown `--parser` /
  `--model` (exit 2) instead of leaving stdout empty.
- Batch conversion skips an existing `.vera` only when it validates and its
  stored `source_file_hash` matches the current PDF, and reports malformed
  archives separately (`malformed_existing`).
- Default PDF pipeline lives in `vera-ingest-pymupdf` (PyMuPDF + pdfplumber +
  selective Tesseract OCR). `vera-ingest` is the provider-neutral registry
  and archive writer.
- PyMuPDF chunk size and overlap labels count whitespace-split words, not
  characters or LLM subword tokens. Docling `chunk_size` uses the same
  whitespace counting (advertised as tokens).

### Breaking

- The `vera-doc` distribution now imports as `vera_doc` (`from vera_doc import VeraDocument`). The previous `import vera` name collided with an unrelated PyPI package. There is no compatibility shim.
- Unknown embedding model / provider names raise an error
  (`UnknownEmbeddingModelError`) instead of silently creating mislabeled
  hashing vectors. The archive records the model that must embed queries at
  search time, so a silent substitute would search against the wrong space.
- Unknown ingest pipeline / `--parser` names raise an error instead of
  falling back to PyMuPDF.
- There is no silent fallback to a different embedding model or ingest
  pipeline when a named provider is missing or fails to load.

### Fixed

- `vera mcp` prints an install hint and exits 2 when the optional `mcp`
  extra is not installed, instead of raising `ImportError`.
- Desktop Convert no longer hangs on the first MiniLM load. The sidecar
  imports Torch on the main thread before it reads stdin. On Windows,
  importing `sentence_transformers` from a convert worker while
  `stdin.readline()` is blocked deadlocks until Stop writes a JSON line.
- PyMuPDF conversion imports `pymupdf` directly, so `vera convert` no longer
  prints a deprecated `fitz` API warning on every run.
- Docling CLI conversion prefetches only Heron ONNX and TableFormer
  accurate (~380 MB) instead of both Heron engines plus TableFormer fast
  (~700 MB), and convert uses the ONNX layout engine.
- Docling `docling_parse/pdf_resources` (fonts/cmaps) must sit next to the
  native parser. Without that tree, convert logged
  `resources-dir does not exist` and rejected the PDF in ~20 ms. Whole-document
  `pypdfium2` fallback now also covers a `FAILURE` status from that backend.
- Docling page-level and page-batch `pypdfium2` recovery no longer fails with
  `multiple values for keyword argument 'page_range'` when retrying a failed
  page.

### Desktop

- File → Open Folder adds the chosen directory to Explorer as a library
  folder (same path as the sidebar Open Folder action).
- Reconvert skips exporting a source PDF when inspect fails and no embedded
  original is present; pipeline and OCR options prefill from inspect.
- Explorer type filters prune files hidden by the filter from the current
  selection.
- Explorer restores the last active library and collapsed inactive folders as
  soon as folders appear, instead of expanding every tree until other folders'
  index-status checks finish.
- Explorer checkboxes set row membership from the native change event so
  unchecking a file cannot leave a stale checkmark while Chat still shows one
  selected document.
- Removed unused `saveVera` / `defaultVeraPath` helpers.
- Shared IPC channel, sidecar action, and stream event names, with a contract
  test that TypeScript `StreamEvent` names match sidecar emissions.
- Split the renderer shell into `AppShell`, `ExplorerSidebar`, `ChatsSidebar`,
  `CenterChatView`, and `CenterSearchView`.
- `npm run app:dev` runs through `scripts/app-dev.js`, which picks `npm.cmd`
  on Windows and `npm` elsewhere before handing off to `uv run`, since `uv`
  does not resolve Windows shims on its own
  ([astral-sh/uv#8770](https://github.com/astral-sh/uv/issues/8770)). It
  installs the `app` and `ml` extras so source-run Convert matches the
  packaged sidecar (PyMuPDF + hashing + MiniLM). Docling remains a CLI extra.
- Fixed a blank-window crash on every launch: the sandboxed preload script's
  restricted `require` cannot load `protocol.ts`'s compiled ES module output
  (or a sibling JSON/CommonJS file by relative path), so `IPC_CHANNELS` threw
  before `contextBridge.exposeInMainWorld` ran and the unhandled renderer
  error left `window.vera` undefined. `preload.cts` now duplicates the
  channel map inline, guarded by a contract test against drift.

### Senior-review fixes

- Index and directory fan-out share one RRF ranking path.
- Search hydrates only the top-k hit chunks, not the full chunk table.
- Sidecar search runs in the background so cancel can land; one cancel primitive.
- Explorer reports when the folder-walk depth cap is hit.
- Auto OCR no longer skips scans whose only native text is headers/boilerplate.
- OCR language codes are sanitized before they become tessdata paths.
- Docling maps real ErrorItem page numbers and recovers when the error has no page list.
- Dotted `KEY=VALUE` tokens stay strings (no float coercion).
- Export writes to the stored basename only.
- MCP search default `top_k` is 10, matching the CLI.
- Ignore sidecar results after a newer call for the same scope.
- `convert()` omitted aliases (`None`) mean pipeline defaults.
- Clamp chunk overlap below `chunk_size` so carry never overruns.
- Consume the skip flag; do not leak it into pipeline options.

Voyage and Ollama embeddings remain pending (they need a query-versus-document
hint). OpenAI ships as `vera-embed-openai`. See [ROADMAP.md](ROADMAP.md).
