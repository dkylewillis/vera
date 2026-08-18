# VERA Roadmap

This roadmap describes the intended direction of VERA. It is not a promise of
specific release dates, and priorities may change as the project develops.

## Release branches

- `main` is the development line for VERA **0.3.x**. Tag `v0.3.0` from
  `main`. The last published 0.2 release is **v0.2.5**; `main` is no longer
  a 0.2 maintenance branch.
- The historical `v0.3` integration branch is tree-identical to `main` and
  is not the source of new 0.3 work. CI still runs on `v0.3` for existing
  open work; new changes should land on `main`.

Package and application versions do not automatically change the `.vera`
format version. The archive format remains 0.2 unless a feature changes its
schema or normative behavior.

The **0.3.0** tag ships the extensibility foundation below (pluggable ingest
and embedders, strict unknown-provider errors, official Docling beside
PyMuPDF, one sidecar interpreter, descriptor APIs). Unchecked items under
Desktop application, Official embedding providers, Packaging and local
models, Future app-managed plugin store, and Additional source formats and
visual grounding are **follow-ups after the 0.3.0 tag** (0.3.1 or later).
They are not blockers for 0.3.0. A packaged plugin host / second Python is
**not** a 0.3.0 shipped item.

## VERA 0.2 — Closed

The last 0.2 software release is **v0.2.5**. Archive format 0.2 remains the
current on-disk format. Do not expect further 0.2.x package releases from
`main`.

## VERA 0.3 — Extensible embeddings

### Provider foundation

- [x] Replace hard-coded model dispatch with a pluggable provider registry.
- [x] Support `provider:model-id` model specifications and existing aliases.
- [x] Discover third-party providers through the `vera.embedders` Python
  entry-point group.
- [x] Expose custom embedding functions through `vera-ingest`.
- [x] Reject unknown model names instead of silently creating mislabeled
  hashing vectors.
- [x] Keep keyword retrieval available when an indexed semantic model provider
  is unavailable.

### Desktop application

- [x] Keep the conversion embedding model separate from the Chat model.
- [x] Persist the selected conversion embedding model.
- [x] Use the selected model for single-file and batch conversion.
- [x] Show installed embedding providers as model-spec suggestions.
- [x] Offer Convert-view presets for hashing and Sentence Transformers MiniLM.
- [x] Advertise provider-owned options through `EmbedderOptions` dataclass
  metadata and `vera.embedder_descriptors` (parallel to ingest pipelines).
- [x] Accept `embedder_options` / `--embedder-option KEY=VALUE` and expose
  `describe_embedding_providers` for schema-driven Convert controls.
- [x] Advertise credential env vars via `capabilities.credential_env` (no
  secrets in Options) and expose `preflight_embedder`.
- [x] Advertise model presets via `vera.embedder_models` /
  `list_embedding_models`.
- [x] Add conversion-time provider and credential preflight checks in the
  Convert UI (sidecar `preflight_embedder`).
- [x] Improve model selection UI with provider-specific model discovery
  (`list_embedding_models`).
- [x] Drive Convert UI embedding forms from descriptors
  (`EmbedderConfigForm` over `PipelineConfigForm`).
- [ ] Store hosted embedding-provider credentials securely in the desktop
  app (`credential_env` via encrypted env secrets) — 0.3.1.

### Official embedding providers

Hosted providers below are follow-ups after 0.3.0 (0.3.1 or later), not
0.3.0 blockers. The descriptor/`credential_env` pattern they will use is
already in 0.3.0.

- [ ] Add a lightweight OpenAI-compatible embeddings provider.
- [ ] Add Voyage AI embeddings for applications that use Claude for answers.
- [ ] Add an Ollama embeddings provider for local models.
- [x] Define supported configuration for endpoints, timeouts, and batch sizes
  via provider `Options` + descriptors (built-ins advertise dimension /
  device / batch_size; hosted plugins follow the same pattern; secrets use
  `credential_env`).
- [x] Document which providers are bundled with each desktop release
  (hashing + MiniLM in the Windows sidecar; hosted embedders in 0.3.1).

### Packaging and local models

- [x] Bundle Sentence Transformers and vendor `all-MiniLM-L6-v2` weights in
  the Windows installer (no first-use Hub download for that model).
- [x] Verify MiniLM files and `sentence-transformers` in packaged sidecar
  describe checks.
- [ ] Add release tests that convert and search with every bundled provider.
  Follow-up after 0.3.0; not a 0.3.0 blocker.

## VERA 0.3 — Extensible ingestion pipelines

### Pipeline foundation

- [x] Define a normalized ingest contract (`IngestResult`) consumed by one
  shared archive writer.
- [x] Add a strict ingest-pipeline registry with `provider[:variant]` specs.
- [x] Discover plugins through the `vera.ingest_pipelines` entry-point group.
- [x] Keep the compatible `pymupdf` pipeline as the default (`vera-ingest-pymupdf`).
- [x] Reject unknown pipeline names instead of falling back to PyMuPDF.
- [x] Move chunking/OCR defaults into pipeline-owned typed options with a thin
  shared `IngestRequest` / opaque `pipeline_options` bag.
- [x] Publish pipeline descriptors for discovery and schema-driven UI forms.
- [x] Keep legacy convert kwargs and CLI flags as compatibility aliases;
  descriptor fields control which aliases are forwarded.

### Optional Docling plugin

- [x] Ship `vera-ingest-docling` with Docling conversion and HybridChunker.
- [x] Map OCR modes, tables, figures, provenance, and contextualized
  embedding text.
- [x] Reject Docling partial-success/failure results in the first release.
- [x] Automatic page-level recovery + `pypdfium2` backend fallback on
  `bad_alloc` / partial success (supersedes blanket reject-on-partial for
  recoverable memory errors); expose `pdf_backend` pipeline option.
- [x] Document first-run model downloads and `DOCLING_ARTIFACTS_PATH`.
- [x] Own Docling defaults (`chunk_size` tokens, `ocr_mode`, `ocr_language`,
  `pdf_backend`) without advertising overlap or OCR DPI.
- [ ] Evaluate Docling quality against representative corpora and decide
  default-vs-optional packaging guidance. Follow-up after 0.3.0; not a
  0.3.0 blocker.

### CLI and source-run desktop

- [x] Expose pipeline selection through `vera convert --parser`.
- [x] Expose provider-owned settings through repeatable
  `vera convert --pipeline-option KEY=VALUE`.
- [x] List installed pipelines from the desktop sidecar.
- [x] Drive Convert settings from `describe_ingest_pipelines` descriptors and
  `PipelineConfigForm`.
- [x] Persist Convert-view `ingest_pipeline` settings for source-run apps.
- [x] Show Docling in the Convert pipeline dropdown as **Advanced layout
  (slower)** in both `app:dev` and the packaged sidecar.
- [x] Bundle `vera-ingest-docling` (Torch, RapidOCR, ONNX Runtime) in the
  one Windows sidecar; model artifacts download on first use into an
  app-owned cache.

### Future app-managed plugin store

0.3.0 uses one interpreter. Official converters are pip packages in that
environment (and a curated freeze in the Windows app). The items below remain
for an app-managed plugin store; a packaged second-Python plugin host is not
a 0.3.0 feature.

- [ ] Let users install, update, enable, disable, and remove extra plugins
  from the application.
- [ ] Keep extra plugins across application upgrades.
- [ ] Define a security and trust policy for third-party plugin installation.

The long-term goal is an app-managed experience for optional extras beyond
the curated sidecar snapshot.

## Additional source formats and visual grounding

Follow-ups after 0.3.0 (0.3.1 or later); not 0.3.0 blockers. Convert, batch
discovery, and the desktop source viewer remain PDF-only until these land.
Design notes: [Additional source formats and visual grounding](docs/multi-format-ingest.md).

Package and application versions still do not change the `.vera` format.
Locator shapes for Markdown, sheets, and slides belong in chunk
`metadata_json` (and viewer attachments). They do not require a 0.2 schema
bump.

### Plugin identity

- [ ] Keep ingest package and provider names tied to the engine
  (`vera-ingest-docling` / `docling`), not the file type
  (`vera-ingest-docling-pdf`).
- [ ] Advertise supported types on `PipelineCapabilities.source_formats`
  and use that list in convert, batch discovery, and file pickers instead of
  hardcoding `.pdf`.
- [ ] Grow formats inside the existing engine package (and optional extras
  for heavy dependencies), not a new plugin per extension.
- [ ] Keep `provider[:variant]` variants as processing strategies
  (`docling:hybrid`), not as `docling:pdf` / `docling:docx`.

### Grounding surfaces

- [ ] Keep PDF visual grounding as page + bbox overlays on the stored
  original PDF. Do not convert PDFs to Markdown in order to highlight them.
- [ ] For flow documents (DOCX, HTML, Markdown, TXT), generate Markdown at
  ingest, store that exact preview as a viewer attachment, and highlight it.
  Keep `source_original` as the real source bytes.
- [ ] Prefer block/heading anchors in the stored Markdown over line numbers
  of generated text (line spans drift on reconvert).
- [ ] Do not treat generated Markdown as the visual source of truth for
  Excel or PowerPoint. Markdown excerpts may still be searchable.
- [ ] Add a `kind` on region locators (`page_bbox`, `text_span`, later
  `sheet_range`) in chunk metadata. Missing `kind` plus a bbox stays
  `page_bbox` so existing archives keep working.
- [ ] Dispatch the desktop viewer by source MIME: PDF overlay, stored
  Markdown preview, or citation text when no overlay applies.

### Later native locators

- [ ] Sheet + A1 range (or row/column spans) for Excel and CSV.
- [ ] Slide index + bbox for PowerPoint.

## Non-goals

- Requiring a user-managed Python installation for normal desktop use.
- Treating an answer model such as Claude as an embedding model.
- Silently falling back to a different embedding model or ingest pipeline.
- Bundling large machine-learning runtimes in the base installer without a
  clear opt-in and distribution plan.
- Encoding the source file type in the ingest plugin package or provider
  name.
- Forcing every source format through PDF page points.
- Bumping `format_version` for new ingest locator shapes.

