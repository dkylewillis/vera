# VERA Roadmap

This roadmap describes the intended direction of VERA. It is not a promise of
specific release dates, and priorities may change as the project develops.

## Release branches

- `main` is the maintenance line for VERA 0.2 bug fixes and compatible
  improvements.
- `v0.3` is the integration branch for features planned for VERA 0.3.
- When VERA 0.3 is ready, `v0.3` will merge into `main` and be tagged
  `v0.3.0`.

Package and application versions do not automatically change the `.vera`
format version. The archive format remains 0.2 unless a feature changes its
schema or normative behavior.

## VERA 0.2 — Maintenance

- Fix defects without intentionally breaking public behavior.
- Improve documentation and diagnostics.
- Preserve archive and API compatibility.
- Backport relevant fixes to the VERA 0.3 development line.

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
- [ ] Add conversion-time provider and credential preflight checks.
- [ ] Improve model selection with provider-specific model discovery.

### Official embedding providers

- [ ] Add a lightweight OpenAI-compatible embeddings provider.
- [ ] Add Voyage AI embeddings for applications that use Claude for answers.
- [ ] Add an Ollama embeddings provider for local models.
- [ ] Store hosted embedding-provider credentials securely.
- [ ] Define supported configuration for endpoints, timeouts, and batch sizes.
- [ ] Document which providers are bundled with each desktop release.

### Packaging and local models

- [ ] Bundle lightweight official providers with the released application.
- [ ] Decide how optional local neural runtimes and models are distributed
  without substantially increasing the base installer.
- [ ] Verify provider availability in packaged sidecar builds.
- [ ] Add release tests that convert and search with every bundled provider.

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
  default-vs-optional packaging guidance.

### CLI and source-run desktop

- [x] Expose pipeline selection through `vera convert --parser`.
- [x] Expose provider-owned settings through repeatable
  `vera convert --pipeline-option KEY=VALUE`.
- [x] List installed pipelines from the desktop sidecar.
- [x] Drive Convert settings from `describe_ingest_pipelines` descriptors and
  `PipelineConfigForm`.
- [x] Persist Convert-view `ingest_pipeline` settings for source-run apps.
- [x] Show Docling in the Convert pipeline dropdown when the plugin is installed.
- [x] Keep packaged-app plugin installation explicitly unsupported for now.

### Future packaged-app plugin runtime

- [ ] Create a plugin runtime separate from the frozen desktop sidecar for
  ingest pipelines (and embedding providers).
- [ ] Decide how Docling/Torch/model artifacts are distributed without
  bloating the base installer.
- [ ] Let users install, update, enable, disable, and remove plugins from the
  application.
- [ ] Keep plugins across application upgrades.
- [ ] Enforce plugin API and VERA version compatibility.
- [ ] Isolate plugin failures from storage, keyword search, and the main app.
- [ ] Define a security and trust policy for third-party plugin installation.

The long-term goal is an app-managed experience. Released VERA installations
should not require users to locate Python, manage a virtual environment, or run
`pip` manually.

## Non-goals

- Requiring a user-managed Python installation for normal desktop use.
- Treating an answer model such as Claude as an embedding model.
- Silently falling back to a different embedding model or ingest pipeline.
- Bundling large machine-learning runtimes in the base installer without a
  clear opt-in and distribution plan.

