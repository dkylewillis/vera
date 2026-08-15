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
Desktop conversions default to the PyMuPDF ingest pipeline and the
offline `hashing` embedder. The Convert view exposes dropdowns for
`ingest_pipeline` (including Docling when installed) and embedding model
presets such as `sentence-transformers:all-MiniLM-L6-v2`, plus a custom
`provider:model-id` field. Chunking and OCR controls are schema-driven: the
sidecar `describe_ingest_pipelines` action supplies descriptors, and
`PipelineConfigForm` renders only advertised fields under a collapsed
**Advanced pipeline options** section (PyMuPDF includes overlap, OCR DPI, and
a Tesseract OCR language dropdown of bundled/downloadable codes plus Custom
for combinations such as `eng+spa`; Docling does not advertise overlap or
DPI). These settings are independent of the Chat
model and are persisted in app settings. `npm run app:dev` installs the `app`
and `ml` extras into the workspace environment. The source-run sidecar matches
packaged releases: it keeps the bundled PyMuPDF pipeline and does not load
Docling. Extra ingest plugins such as Docling run from a trusted external
Python environment under **File > LLM Providers**. Install plugins with
`python -m pip install vera-ingest-docling` or
`python -m pip install -e <clone>`, then Validate / Refresh. An unavailable
selection is disabled or fails with the resolver error. Docling's first conversion may download Hugging Face
models; save an optional token under **File > LLM Providers → Hugging Face**
(or set `HF_TOKEN` in the environment / a local `.env` from `.env.example`) to
raise Hub rate limits. Conversion progress and the current filename appear in
the footer status bar, so progress remains visible when you switch away from
the Convert view. Right-click a folder in Explorer and choose **Convert PDFs…**
to open directory conversion for that folder. To rebuild an existing archive with a different ingest
pipeline or embedding model, right-click the `.vera` file in Explorer and
choose **Reconvert…**; Convert opens immediately with a preparing status while
the archive is read, then prefills the current settings and turns overwrite on.
In Explorer, click a file to select it, Ctrl/Cmd+click to add or remove it, and
Shift+click to select a range. The checkbox next to a file adds or removes that
row from the same list — unchecking it deselects it, and the highlight and the
Chat/Search “selected document” count stay in sync. Selected `.vera` files become the Search/Ask
scope and selected PDFs become the Convert list. Click the folder name, empty
Explorer space, or press Escape to search the whole library again.
Use the **Chat / Search** switch above the center workspace to choose between
LLM-backed conversation and direct retrieval. Search supports hybrid, semantic,
and keyword modes from its composer options. Its ranked passage cards open and
highlight the matching source in the document viewer without adding the query
to chat history. Source loading remains independent of library inspection,
conversion, and indexing. Selecting another citation supersedes the earlier
source request. Large manuals copy into a local viewer cache; if a matching
PDF sits next to the `.vera` file, that sibling is used instead of extracting
the embedded original. A source load that does not settle within five minutes
is cancelled with an error instead of leaving a permanent footer status.

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
that library. Right-click a folder and choose **Build index** or **Update
index** to start immediately without that dialog; the badge and footer show
progress. Use **Inspect** in the Info view only when you need library
metrics or to revalidate every archive; that operation can take substantially
longer for large libraries. Inspection runs on a sidecar worker and the footer
reports completed and total archives, the current filename, cumulative chunks,
and skipped files. Its request-scoped status clears on either success or
failure, independently of simultaneous indexing or conversion activity.

After a build or update starts, indexing runs in the background. The
folder's index badge spins. The footer shows completed archives, total archives,
the current phase and filename, indexed chunks, and skipped-file count. It
switches to a finalizing phase while the validated generation is published. You
can continue browsing and using Search or Ask while the existing index, or
recursive fallback search, remains available. A completed warning badge means
some archives were skipped; select it to review the latest indexing report.

On startup, Explorer collapses inactive folders immediately so every library
header stays visible and the last active library stays expanded. Folders show
their last verified badge state while VERA checks the current filesystem in
the background. A neutral spinner is shown when there is no saved status yet,
rather than treating the folder as unindexed.

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

## External Python plugins

Source-run (`npm run app:dev`) and packaged builds keep search, Ask, indexing,
and bundled PyMuPDF conversion in the sidecar. To use extra ingest or embedding
plugins:

1. Create a virtual environment with Python 3.10+ and install a compatible
   `vera-ingest` 0.3.x plus the plugin:
   ```bash
   python -m venv C:\venvs\vera-plugins
   C:\venvs\vera-plugins\Scripts\python.exe -m pip install vera-ingest vera-ingest-docling
   C:\venvs\vera-plugins\Scripts\python.exe -m pip install vera-your-embedder
   python -m pip install -e C:\src\my-vera-plugin
   ```
   Adding a clone to `PYTHONPATH` without installing it is not enough. Install
   embedder plugins in the same environment as extra parsers.
2. In VERA, open **File > LLM Providers**, enable **External Python plugins**,
   choose that environment's `python.exe`, and click **Validate** once.
3. Convert lists extra parsers and embedders as `(external)`. Bundled
   `pymupdf`, `hashing`, and `sentence-transformers` win when a plugin repeats
   those names. After installing or updating plugins, click **Refresh plugins**.
   Embedder `credential_env` secrets are saved under the same settings page and
   forwarded to the sidecar and plugin host. Convert calls `preflight_embedder`
   before writing an archive.

On later launches VERA re-probes the saved interpreter in the background and
refreshes Convert when that probe succeeds. You do not need to Validate after
every launch. First discovery can take about a minute when Docling or Torch
imports are cold; Convert may show Docling as not installed until that probe
finishes.

The selected environment must provide `vera-ingest` 0.3.x (plugin API version
1) and a compatible `vera-doc`. Ingest plugins register under
`vera.ingest_pipelines`; embedders register under `vera.embedders`. Optional
Hugging Face tokens, embedder `credential_env` secrets, and the **Model cache**
field (`DOCLING_ARTIFACTS_PATH`) are forwarded to the plugin host. See
[Creating an ingest pipeline plugin](creating-an-ingest-pipeline.md) and
[Creating an embedding provider](creating-an-embedding-provider.md).
Which process runs convert versus embed is in
[Convert routing](desktop-app-architecture.md#convert-routing).

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
- **Validate fails for the external Python environment** — choose an absolute
  interpreter path that exists, install `vera-ingest` 0.3.x into that
  environment, then Validate again. A cold Docling/Torch import can take about
  a minute; the status stays on “Checking the Python environment…” until the
  probe finishes. A timeout from an earlier attempt should not appear the
  moment you click Validate.
- **An extra parser or embedder is missing from Convert** — install it with
  `python -m pip install` or `python -m pip install -e <clone>` in the selected
  environment, then **Refresh plugins**. After a relaunch, wait for the
  automatic re-probe before treating the plugin as missing. Raw `PYTHONPATH`
  folders are not discovered. If Search warns that semantic groups were
  skipped, the embedder used at convert time is not available in the current
  sidecar or plugin host.

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
