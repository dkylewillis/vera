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

## Future — Managed third-party plugins

- [ ] Create a plugin runtime separate from the frozen desktop sidecar.
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
- Silently falling back to a different embedding model.
- Bundling large machine-learning runtimes in the base installer without a
  clear opt-in and distribution plan.

