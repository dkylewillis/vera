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

Opening a workspace folder activates it as the default Search and Ask scope
without opening the corpus. Activation is instantaneous: it sets the active
library path, clears file-selection overrides, and refreshes the index badge
in the background. The corpus is opened on the first Search or Ask request.
Cached library summaries from an earlier Inspect are restored when
available. Selecting a library folder activates its Search/Ask scope and resets
the viewer to an empty document view; selecting an individual `.vera` scope
does not replace an open preview. Previewing an archive does not replace the
library scope. Checking one or more archives in Explorer
explicitly narrows retrieval to those files; clearing the checks restores
whole-library search. Chat sessions persist the scope path so reopening a
library-backed conversation restores its context.

The center workspace has **Chat** and **Search** modes. Chat keeps LLM-backed
conversations and their history, while Search runs direct hybrid, semantic, or
keyword retrieval without adding turns to a conversation. Both modes use the
same thread-and-composer layout. Search renders the query as a user message and
ranked passage results as selectable response cards; selecting a result opens
and highlights its source in the document viewer. Retrieval controls remain
available beneath the Search composer. Explorer, chat history, and conversion
remain sidebar views.

The app checks the folder's local collection index when the folder is added,
activated, refreshed, changed by the watcher, or receives a newly converted
archive:

- **Indexed** means the index is fresh and is used automatically.
- **Stale** means files changed after the last build.
- **No index** means no collection index has been built yet.

A fresh persistent index is used automatically for Search and Ask. The document
viewer's **Info** tab keeps **Inspect** available for an explicit validation
scan of a library and shows document inspection, validation, export, and page
text details beside the source they describe. Individual archive metadata is
inspected automatically when Document Info opens, so only Library Info exposes
the explicit **Inspect** action. Double-clicking a library opens a dedicated
**Library Info** state; single-clicking only changes the active Search/Ask
scope and leaves the viewer on its document view, empty when no document is
loaded. Library Info does not expose a Document tab or pass the directory to
the source-document loader, and its **Models**
field lists every embedding-model group represented in the library index. It
also shows document and chunk coverage, index freshness and reasons,
recursive/exclusion settings, skipped archives, storage usage,
generation/build/check timestamps, and per-model dimensions and counts. Its
close action clears the viewer in the same way as closing a document preview.
Libraries with at least 100
discovered archives prompt to build or update an unavailable index, while smaller
libraries expose build, update, rescan, show-in-system-folder, and
close actions in the folder row's context menu. File rows offer show-in-system-
folder (and preview/trash where applicable). Clicking a PDF selects it and
seeds Convert defaults without switching to the Convert view; Ctrl/Cmd+click
toggles additional PDFs into a conversion multi-select (separate from `.vera`
search-scope checkboxes). Clicking a `.vera` sets Search/Ask scope without
changing the document viewer. Double-click or right-click **View in document
viewer** / **Preview embedded source** loads that PDF or archive original in
the source pane; when multiple PDFs are selected, right-click also offers
**Convert selected**. The same menus can be opened from the keyboard with
Shift+F10 or the Menu key, support arrow key navigation, and close with
Escape. Show-in-folder opens a library directory in the OS file manager, or
reveals a selected `.vera`/`.pdf` file in its parent folder. Explorer keeps
the active-folder highlight without an Active text label, including when
selected files override the library, and represents index state with a compact
database badge: green for a fresh index and orange when an index is missing or
stale. A blue spinning badge means a build or update is running in the
background; after completion, a warning badge opens the report when archives
were skipped. Choosing **Search anyway** never blocks retrieval: the sidecar
performs recursive fan-out search and the app keeps a slower-search banner
visible. Watcher events and completed directory conversions update badges but
never start a build automatically. Double-clicking a library folder activates
it and opens its Library Info view, clearing any document preview while leaving
the library available as the Search/Ask scope.

Any readable folder can remain active even before it contains a `.vera`
archive. Search and Ask open the corpus on demand; an empty library returns a
clear error instead of leaving the folder inactive. Other `VeraCorpus.open`
callers retain the strict non-empty default unless they pass `allow_empty`.

Builds and updates run on a sidecar worker thread without using the app's global
busy state, so document browsing, Search, and Ask remain available. The folder
badge carries progress and completion state instead of leaving a modal open.
Selecting a completed badge opens the latest report, including indexed/chunk
counts and invalid or embedding-incompatible archives that were skipped. Index
publication remains atomic in `vera-doc`, so concurrent searches use the
previous valid generation until the new generation is published, and a failed
build does not replace it.

## Batch PDF Conversion

The Convert PDF view supports a single archive, an Explorer multi-selection of
PDFs, or an entire directory. Opening the view (or switching Single PDF /
Selected / PDF Directory) prefills paths from the latest Explorer selection: a
PDF or `.vera` seeds single-file conversion, a non-empty PDF multi-select opens
**Selected**, and a folder or active library seeds directory conversion.
Directory conversion can include nested folders. Selected and directory modes
create each `.vera` archive beside its source PDF using the same base filename
(`proposal.pdf` becomes `proposal.vera`). Existing archives are validated
before they are skipped; malformed outputs are reported separately, and
overwrite must be selected explicitly. Conversion uses selective
PyMuPDF/Tesseract OCR for image-based low-text pages with English language data
bundled into both `vera-doc` and the packaged sidecar. It publishes a validated
temporary sibling atomically, preserves an existing destination after failure,
and rejects PDFs with no searchable text after OCR with an OCR-specific
message. Sidecar `convert` and `batch_convert` requests accept optional
`ocr_mode`, `ocr_language`, and `ocr_dpi` fields and otherwise use `auto`,
`eng`, and `300`. `batch_convert` also accepts an explicit `paths` list of PDF
files; when present, directory discovery is skipped. The sidecar continues
after per-file failures and returns converted, skipped, malformed, and failed
counts plus individual diagnostics. During multi-file conversion the UI shows
the current file path and offers **Skip** (continue with the next PDF) and
**Stop** (abort the batch). Workspace folders refresh after the batch, allowing
an existing collection index to become visibly stale without being rebuilt
automatically. The same public `vera-doc` operation powers
`vera convert <directory> --recursive`, keeping desktop and CLI behavior
aligned.

## Development Commands

From the repo root:

```bash
npm run app:install
npm run app:dev
npm run app:typecheck
npm run app:build
npm run app:dist
```

`npm run app:dist` packages the Python sidecar through
`packages/vera-app/scripts/build-sidecar.cjs`, which runs PyInstaller with the
project virtualenv when it is available (honoring `VERA_SIDECAR_PYTHON`) and
otherwise falls back to `uv run --extra app --extra sidecar`. Bundled Tesseract
English data is passed as an absolute path so the build works from any
directory.

From the repo root:

```bash
uv run --extra dev python -m pytest -q
```

## Source Document Viewer

The `source` sidecar action accepts either a `.vera` archive or a filesystem
`.pdf`. Archives materialize the embedded source attachment; PDF paths are
copied into the same hash-keyed cache under Electron's userData
`source-cache/` directory. Both return metadata plus `cache_path`. Electron
rewrites that path to a privileged `vera-source://cache/...` URL and serves
the bytes with `protocol.handle`, so PDF.js can fetch the document without
shipping multi‑MB base64 through the JSON-Lines IPC channel (which previously
froze the UI on large PDFs).

The renderer PDF viewer (PDF.js) defaults to fit-width zoom so pages fill the
source pane without horizontal cropping, and also supports fit-page, page
navigation (previous/next and an editable page field), discrete zoom steps with
Ctrl/Cmd+wheel and standard zoom hotkeys, and viewport-preserving zoom so the
visible page stays put when scale changes. Manual zoom is temporary: resizing
the source pane (or window) snaps back to fit-width, while an explicit fit-page
choice continues to reflow on resize. Pages render at device pixel ratio for
sharper output on HiDPI displays. Citation passage and figure highlights can be
toggled, with a compact color legend when both are present. The viewer chrome
can hide the pane (keeping a right-edge toggle) or expand it by hiding chat so
the document fills from the left sidebar to the window edge. Closing the open
document clears its preview, selection, and highlights while leaving the viewer
pane, active library, and Search/Ask scope intact. When the displayed source
was extracted from a `.vera` archive, the viewer's **Info** tab
that inspects that archive and shows its format, source, page and chunk counts,
embedding model and dimensions, creation time, archive size, parser and
chunking settings, OCR summary, attachment count, validation status, and
export controls alongside the PDF.

## Near-Term App Work

- Replace the extractive cited draft in `answer` with configurable LLM provider calls that preserve citation ids.
- Add recent document shortcuts.
- Add richer conversion progress events from the sidecar.
- Add settings for provider configuration and app defaults.
