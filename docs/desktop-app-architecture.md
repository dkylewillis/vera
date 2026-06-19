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
- `export`
- `source`
- `page`

This keeps the app UI independent from Python internals while preserving a simple local development loop.

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
- Add library folder persistence and recent archive shortcuts.
- Add richer conversion progress events from the sidecar.
- Add settings for provider configuration and app defaults.
