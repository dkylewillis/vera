# VERA Roadmap

This roadmap describes the intended direction of VERA. It is not a promise of
specific release dates, and priorities may change as the project develops.

## Release branches

- `main` is the development line for VERA **0.3.x**. **v0.3.0** is published
  (PyPI and GitHub Releases, including `VERA.Setup.0.3.0.exe`). Unreleased
  work on `main` is the next 0.3.x; do not republish 0.3.0. The last 0.2
  release is **v0.2.5**.
- The historical `v0.3` integration branch has been deleted. CI and docs
  workflows run on `main`. New changes should land on `main`.

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
- [x] Offer Convert-view presets for hashing, Sentence Transformers MiniLM,
      and OpenAI `text-embedding-3-*`.
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
- [x] Store hosted embedding-provider credentials securely in the desktop
      app (`credential_env` via encrypted env secrets). Settings → Embeddings
      stores `OPENAI_API_KEY`.

### Official embedding providers

OpenAI ships as the official `vera-embed-openai` plugin (stdlib HTTP, frozen
into the Windows sidecar). Voyage and Ollama wait on an optional
query-versus-document hint on `EmbeddingFunction`: convert and search share
one `embed(texts)` today, and those providers need `input_type` or
`search_document:` / `search_query:` prefixes.

- [x] Add a lightweight OpenAI embeddings provider (`vera-embed-openai`).
- [ ] Add Voyage AI embeddings for applications that use Claude for answers.
      Blocked until `EmbeddingFunction` can hint query vs document.
- [ ] Add an Ollama embeddings provider for local models. Same protocol
      prerequisite as Voyage. A generic `openai-compatible` provider with a
      required explicit endpoint is cleaner than overloading `OPENAI_BASE_URL`.
- [x] Define supported configuration for endpoints, timeouts, and batch sizes
  via provider `Options` + descriptors (built-ins advertise dimension /
  device / batch_size; hosted plugins follow the same pattern; secrets use
  `credential_env`).
- [x] Document which providers are bundled with each desktop release
      (hashing + MiniLM + OpenAI in the Windows sidecar).
- [ ] Cancellation and progress during embed. Convert currently passes every
      chunk to `embedder.embed(...)` in one call; Cancel is ignored until that
      returns, and there is no per-batch progress. A protocol hook is a
      follow-up, not a plugin-local fix.

### Packaging and local models

- [x] Bundle ONNX Runtime MiniLM and vendor a VERA-exported `all-MiniLM-L6-v2`
  graph in the Windows installer (no first-use Hub download; no Torch).
- [x] Verify MiniLM files and the `sentence-transformers` provider name in
  packaged sidecar describe checks.
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
- [x] Keep 0.3.0 desktop Convert PyMuPDF-only. Docling stays a CLI extra
  (`vera-cli[docling]`); it is not listed in Convert and is not frozen into
  Setup.exe.
- [ ] Revisit bundling Docling, a lighter layout engine, or a hosted layout
  API as another ingest provider after 0.3.0.

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

Markdown ingest ships: `vera convert notes.md` uses the bundled `markdown`
pipeline in `vera-ingest`, directory discovery includes `.md` / `.markdown`,
and the desktop source viewer highlights `text_span` lines. Follow-ups
(DOCX, HTML, Excel, PPTX) remain after 0.3.x. Design notes:
[Additional source formats and visual grounding](docs/multi-format-ingest.md).

Package and application versions still do not change the `.vera` format.
Locator shapes for Markdown, sheets, and slides belong in chunk
`metadata_json` (and viewer attachments). They do not require a 0.2 schema
bump.

### Plugin identity

- [x] Keep ingest package and provider names tied to the engine
  (`vera-ingest-docling` / `docling`), not the file type
  (`vera-ingest-docling-pdf`). Markdown lives inside `vera-ingest` as
  provider `markdown`.
- [x] Advertise supported types on `PipelineCapabilities.source_formats`
  and use that list in convert, batch discovery, and file pickers instead of
  hardcoding `.pdf`.
- [ ] Grow formats inside the existing engine package (and optional extras
  for heavy dependencies), not a new plugin per extension.
- [x] Keep `provider[:variant]` variants as processing strategies
  (`docling:hybrid`), not as `docling:pdf` / `docling:docx`.

### Grounding surfaces

- [x] Keep PDF visual grounding as page + bbox overlays on the stored
  original PDF. Do not convert PDFs to Markdown in order to highlight them.
- [ ] For flow documents (DOCX, HTML, TXT), generate Markdown at
  ingest, store that exact preview as a viewer attachment, and highlight it.
  Keep `source_original` as the real source bytes. Native `.md` already
  stores the original Markdown and highlights `text_span` lines.
- [ ] Prefer block/heading anchors in the stored Markdown over line numbers
  of generated text (line spans drift on reconvert).
- [ ] Do not treat generated Markdown as the visual source of truth for
  Excel or PowerPoint. Markdown excerpts may still be searchable.
- [x] Add a `kind` on region locators (`page_bbox`, `text_span`, later
  `sheet_range`) in chunk metadata. Missing `kind` plus a bbox stays
  `page_bbox` so existing archives keep working.
- [x] Dispatch the desktop viewer by source MIME: PDF overlay, stored
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

