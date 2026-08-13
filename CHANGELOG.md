# Changelog

Notable changes to VERA software, CLI, and Python APIs.

**0.3.x versions the packages, CLI, and desktop app.** The `.vera` archive
format remains **0.2**. Existing archives are compatible; you do not need to
reconvert files created with 0.2 tooling in order to search or inspect them.

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
- Optional Docling plugin (`vera-ingest-docling`) registering
  `docling` / `docling:hybrid`, with HybridChunker, RapidOCR, first-run
  model-download notes, and `pdf_backend` recovery on page-level memory
  errors.
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

- Typed `Citation` on search hits (`result.citation`) plus configurable hybrid
  `semantic_weight` / `keyword_weight` on `VeraDocument.search()`.
- Shared `vera_ingest.viewer.result_payload()` serializer for CLI, MCP, and
  desktop search JSON.
- Vectorized semantic scoring, batched attachment loads, and FTS writes that
  align `chunks_fts.rowid` with `chunks.rowid` (format 0.2 compatible; legacy
  archives fall back to deleting by `chunk_id`).
- `VeraDocument.iter_raw_chunks()` / `format_metadata()` for library indexing
  without private `VeraDocument` access.

### Changed

- `EmbedderOptions` and `PipelineOptions` `from_mapping` reject integers
  outside advertised `minimum`/`maximum` (hashing `dimension` 8–4096,
  pipeline `chunk_size` 100–3000).
- Conversion writes a validated temporary sibling and publishes atomically.
  Empty (no searchable chunks) conversions fail with an OCR-oriented message.
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

### Desktop

- File → Open Folder adds the chosen directory to Explorer as a library
  folder (same path as the sidebar Open Folder action).
- Reconvert skips exporting a source PDF when inspect fails and no embedded
  original is present; pipeline and OCR options prefill from inspect.
- Explorer type filters prune files hidden by the filter from the current
  selection.
- Removed unused `saveVera` / `defaultVeraPath` helpers.
- Shared IPC channel, sidecar action, and stream event names, with a contract
  test that TypeScript `StreamEvent` names match sidecar emissions.
- Split the renderer shell into `AppShell`, `ExplorerSidebar`, `ChatsSidebar`,
  `CenterChatView`, and `CenterSearchView`.
- `npm run app:dev` uses `npm` instead of Windows-only `npm.cmd`.

Hosted embedding providers, Convert UI embedder preflight/forms, and a
packaged-app plugin runtime are follow-ups after this tag (0.3.1 or later).
See [ROADMAP.md](ROADMAP.md).
