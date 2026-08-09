# Run the desktop app

VERA's desktop app is an Electron application with a React interface and a
local Python sidecar. Windows users can install the packaged app from
[GitHub Releases](https://github.com/dkylewillis/vera/releases). The remaining
sections describe running and packaging it from a repository checkout.

## Install the Windows app

Download the `VERA Setup <version>.exe` installer from the
[latest GitHub Release](https://github.com/dkylewillis/vera/releases), run it,
and then open VERA from the Start menu.

## Requirements

- Git
- Python 3.10 or newer
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Node.js and npm
- Windows (the current root development script and packaged build target Windows)

## Clone the repository

```bash
git clone https://github.com/dkylewillis/vera.git
cd vera
```

All remaining commands in this guide run from the repository root.

## Install the app dependencies

Install the Electron and React dependencies:

```bash
npm run app:install
```

The development command uses `uv` to create or update the Python environment
and install the `vera-app` sidecar and `vera-doc` engine.

## Start the development app

```bash
npm run app:dev
```

This starts the Vite development server and then opens the Electron window.
Keep the terminal running while using the app. Press `Ctrl+C` in that terminal
to stop both processes.

Open a PDF from the app's Convert view to create a `.vera` archive, or use the
native File menu to open an existing archive or document library.
Desktop conversions default to the built-in PyMuPDF ingest pipeline and the
offline `hashing` embedder. The Convert view exposes dropdowns for
`ingest_pipeline` (including Docling when installed) and embedding model
presets such as `sentence-transformers:all-MiniLM-L6-v2`, plus a custom
`provider:model-id` field. These settings are independent of the Chat model and
are persisted in app settings. `npm run app:dev` installs the `app`, `ml`, and
`docling` extras into the workspace environment so both plugins are available
for GUI testing. Packaged releases do not bundle optional ingest plugins or
Sentence Transformers; an unavailable selection is disabled or fails with the
resolver error. Conversion progress and the current filename appear in the
footer status bar, so progress remains visible when you switch away from the
Convert view.

Use the **Chat / Search** switch above the center workspace to choose between
LLM-backed conversation and direct retrieval. Search supports hybrid, semantic,
and keyword modes from its composer options. Its ranked passage cards open and
highlight the matching source in the document viewer without adding the query
to chat history. Source loading remains independent of library inspection,
conversion, and indexing. Selecting another citation supersedes the earlier
source request, and a source load that does not settle within two minutes is
cancelled with an error instead of leaving a permanent footer status.

When **Figures** is enabled, Search initially returns only figure metadata and
captions. Selecting a result loads image previews for that result's referenced
figures on demand; unselected result images are not read or sent through the
sidecar connection.

## Large document libraries

Collection indexes are persistent: the app checks their freshness when a
library is activated but does not rebuild them automatically. Activating a
folder only sets the Search and Ask scope; the corpus opens on the first
query. A fresh index makes that first search fast. If an index is missing or
stale, the first Search or Ask prompts you to build or update it; choose
**Don&apos;t ask again** to keep using recursive search without future prompts for
that library. Use **Inspect** in the Info view only when you need library
metrics or to revalidate every archive; that operation can take substantially
longer for large libraries. Inspection runs on a sidecar worker and the footer
reports completed and total archives, the current filename, cumulative chunks,
and skipped files. Its request-scoped status clears on either success or
failure, independently of simultaneous indexing or conversion activity.

After you confirm a build or update, indexing runs in the background. The
folder's index badge spins. The footer shows completed archives, total archives,
the current phase and filename, indexed chunks, and skipped-file count. It
switches to a finalizing phase while the validated generation is published. You
can continue browsing and using Search or Ask while the existing index, or
recursive fallback search, remains available. A completed warning badge means
some archives were skipped; select it to review the latest indexing report.

On startup, folders show their last verified badge state while VERA checks the
current filesystem in the background. A neutral spinner is shown when there is
no saved status yet, rather than treating the folder as unindexed.

Parent and empty folders can also be activated as libraries. Nested `.vera`
files are discovered recursively when there is no saved index configuration.
A folder with no `.vera` files remains active and watched; Search and Ask
report that nothing is searchable until archives are present.

## Check or build the app

Run the TypeScript checks:

```bash
npm run app:typecheck
```

Build the renderer and Electron main process:

```bash
npm run app:build
```

Create an unpacked desktop build, including the packaged Python sidecar:

```bash
npm run app:dist
```

On Windows, the unpacked executable is written to
`packages/vera-app/release/win-unpacked/VERA.exe`.

Create the distributable Windows installer:

```bash
npm run app:release
```

This removes the existing `packages/vera-app/release` directory, rebuilds the
app and Python sidecar, and writes an NSIS installer into that directory.

## Common startup problems

- **`uv` is not recognized** — install `uv`, open a new terminal, and rerun the
  command from the repository root.
- **`npm` is not recognized** — install Node.js, open a new terminal, and
  confirm `node --version` and `npm --version` work.
- **Electron dependencies are missing** — rerun `npm run app:install`.
- **The Electron window does not open** — check the `npm run app:dev` terminal
  for a Python sidecar, TypeScript, Vite, or port error before restarting it.
- **`Failed to update Windows PE resources` / `uv-trampoline` Access denied** —
  Windows Defender or corporate EDR is locking uv's temporary launcher while
  uv installs a package that ships a console script. The sidecar build prefers
  the project virtualenv (`.venv`) and only falls back to `uv run`, so install
  PyInstaller once and rebuild:

  ```bash
  uv pip install "pyinstaller>=6"
  npm run app:dist
  ```

  Set `VERA_SIDECAR_PYTHON` to use a different interpreter, or exclude the
  repository and `%TEMP%` from real-time scanning, then retry.

## Provider request errors

LLM authentication, credit, rate-limit, and model errors appear in a compact,
dismissible banner. The failed prompt is restored in the composer so it can be
edited or retried without restarting the app. HTTP 401 and 403 errors usually
require checking the saved API key or account permissions; HTTP 402 errors
require provider credits or a lower-cost model.

If a provider has no endpoint that supports image input, VERA retries the
request with text only and adds a note to the assistant response explaining
that the images were omitted.

While an answer is generating, the send button becomes a stop button. Selecting
it cancels only that answer, stops its active provider stream, and saves the
user prompt plus any streamed response received so far without restarting the
local sidecar. Answer prose appears incrementally as provider tokens arrive.
VERA withholds inline tool-call markup and clears any provisional prose from a
turn that ultimately invokes a retrieval tool, so only the final grounded
answer remains visible.

For implementation details and the sidecar protocol, see the
[desktop app architecture](desktop-app-architecture.md).
