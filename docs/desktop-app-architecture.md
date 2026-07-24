# VERA Desktop App Architecture

## Decision

`vera-app` is a desktop application, not a browser-served web app.

The app uses Electron with a React/TypeScript renderer for the desktop shell and a Python sidecar for document operations. The sidecar imports `vera-doc` directly and communicates with Electron over a JSON Lines protocol on stdio.

## Why Electron

Electron fits the product shape VERA is moving toward:

- local file and folder workflows
- PDF/document workspace UI
- sidebars, tabs, command palette, settings, and keyboard-driven interaction
- mature PDF.js and web rendering ecosystem
- normal desktop packaging path for Windows/macOS/Linux

Tauri remains a possible future optimization if app size becomes the dominant concern. PySide/PyQt would keep more code in Python but would make a polished document workstation UI more expensive to build.

## Package Boundaries

```text
packages/
  vera-doc/   # Python document engine and importable `vera` package
  vera-cli/   # terminal interface over vera-doc
  vera-app/   # Electron desktop app plus Python sidecar
```

Dependency direction stays one-way:

```text
vera-cli -> vera-doc
vera-app -> vera-doc
```

`vera-app` should not shell out to `vera-cli` for normal product behavior. The CLI is a user interface; the app backend should call `vera-doc` directly.

## Sidecar Protocol

The Electron main process starts:

```bash
python -m vera_app.sidecar
```

Requests and responses are newline-delimited JSON. Each request carries an `id` and an `action`; responses echo the `id` and return either `ok: true` with `result`, or `ok: false` with `error`.

Initial actions:

- `ping`
- `inspect`
- `validate`
- `search`
- `answer`
- `convert`
- `batch_convert`
- `export`
- `source`
- `page`
- `index_status`
- `index_build`
- `index_update`

This keeps the app UI independent from Python internals while preserving a simple local development loop.

## Active Libraries and Collection Indexes

Opening a workspace folder activates it as the default Search and Ask scope. The active library is independent from the document viewer: opening a `.vera` file for review does not replace the library scope. Checking one or more archives in Explorer explicitly narrows retrieval to those files; clearing the checks restores whole-library search. Chat sessions persist the scope path so reopening a library-backed conversation restores its context.

The app checks the folder's local collection index when the folder is added, activated, refreshed, changed by the watcher, or receives a newly converted archive:

- **Indexed** means the index is fresh and is used automatically.
- **Stale** means files changed after the last build.
- **No index** means no collection index has been built yet.

Missing indexes prompt for a build with recursive discovery enabled by default and optional line-separated exclusions. Stale indexes prompt for an update using their saved settings. Choosing **Search anyway** never blocks retrieval: the sidecar performs recursive fan-out search and the app keeps a slower-search banner visible. Watcher events update badges and prompts but never start a build automatically.

Builds and updates use the app's blocking busy state. Their completion report includes indexed/chunk counts and lists invalid or embedding-incompatible archives that were skipped. Index publication remains atomic in `vera-doc`, so a failed build does not replace the previous valid generation and Windows readers can keep using an open generation during an update.

## Batch PDF Conversion

The Convert PDF view supports a single archive or an entire directory. Directory conversion can include nested folders and creates each `.vera` archive beside its source PDF using the same base filename (`proposal.pdf` becomes `proposal.vera`). Existing archives are skipped by default; overwrite must be selected explicitly. The sidecar continues after per-file failures and returns converted, skipped, and failed counts plus individual errors. Workspace folders refresh after the batch, allowing an existing collection index to become visibly stale without being rebuilt automatically. The same public `vera-doc` operation powers `vera convert <directory> --recursive`, keeping desktop and CLI behavior aligned.

## Development Commands

From the repo root:

```bash
npm run app:install
npm run app:dev
npm run app:typecheck
npm run app:build
npm run app:dist
```

From the repo root:

```bash
uv run --extra dev python -m pytest -q
```

## Near-Term App Work

- Replace the extractive cited draft in `answer` with configurable LLM provider calls that preserve citation ids.
- Keep Source Document PDF rendering responsive for very large source documents.
- Add recent document shortcuts.
- Add richer conversion progress events from the sidecar.
- Add settings for provider configuration and app defaults.
