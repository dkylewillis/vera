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
- Source-run (`npm run app:dev`) works on Linux, macOS, and Windows. The
  packaged installer currently targets Windows only.

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
`ingest_pipeline` (PyMuPDF in 0.3.0) and
embedding model presets such as `sentence-transformers:all-MiniLM-L6-v2`, plus
a custom `provider:model-id` field. Chunking and OCR controls are schema-driven:
the sidecar `describe_ingest_pipelines` action supplies descriptors, and
`PipelineConfigForm` renders only advertised fields under a collapsed
**Advanced pipeline options** section (PyMuPDF includes overlap, OCR DPI, and
a Tesseract OCR language dropdown of bundled/downloadable codes plus Custom
for combinations such as `eng+spa`). These settings are independent of the Chat
model and are persisted in app settings. `npm run app:dev` installs the `app`
extra into the workspace environment. The source-run
sidecar matches packaged releases: one Python process with PyMuPDF,
hashing, and ONNX MiniLM. Plugins are ordinary pip packages in **the same environment**
(`vera.ingest_pipelines` / `vera.embedders`); CLI users can
`pip install "vera-cli[docling]>=0.3.0"` or `pip install -e <clone>` after
`vera-ingest` 0.3.x. An unavailable selection is disabled or fails with the
resolver error. Save an optional token under **File > Settings → Hugging Face**
(or set `HF_TOKEN` in the environment / a local `.env` from `.env.example`) for
Hub access used by extras. Conversion progress and the current filename appear in
the footer status bar, so progress remains visible when you switch away from
the Convert view. **File > Open convert log...**, Convert **Open log**, and
**Settings → Diagnostics** open the same append-only file
(`userData/logs/sidecar.log`: `%APPDATA%\VERA\logs\sidecar.log` when packaged,
`%APPDATA%\@vera\app\logs\sidecar.log` in `app:dev`). Timed convert
steps (`elapsed_ms`) go there so freeze vs `.venv` times can be
compared; CLI `vera convert` still prints those lines on stderr only.
Right-click a folder in Explorer and choose **Convert PDFs…**
to open directory conversion for that folder. To rebuild an existing archive with a different ingest
pipeline or embedding model, right-click the `.vera` file in Explorer and
choose **Reconvert…**; Convert opens immediately with a preparing status while
the archive is read, then prefills the current pipeline, embedding, and OCR
settings and turns overwrite on. If inspect fails and no sibling PDF is
listed, Reconvert does not export an embedded original and shows
**Could not read archive metadata**. Place the matching `.pdf` next to the
archive, or export the original from Document Info once the archive is
readable.
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
to chat history. CLI and MCP search return the full ranked list; they do not
apply Ask's relative `quality` filter.

### Customize Ask modes

Built-in Chat modes are **Ask**, **Research**, and **Summarize**. Each is a
Markdown file: YAML-ish frontmatter sets retrieval defaults, and the body is
the system prompt. User files live in Electron `userData/modes` (in
`npm run app:dev` on Windows, `%APPDATA%\@vera\app\modes`). On first launch
the app copies `ask.md` and `research.md` into that folder if they are
missing so you can edit them; `summarize.md` stays package-only until you
add a file. User files override built-ins with the same `id`.

Open the folder from **File → Answer Modes Folder…** or the mode picker's
**Open modes folder…**. Click **Reload modes** (or restart) after edits.
Only flat `key: value` frontmatter is parsed; nested YAML is treated as
prompt body. Clamped fields:

| Field | Default | Allowed |
| --- | --- | --- |
| `id` | slug of `name` | stable identifier |
| `search_mode` | `hybrid` | `hybrid`, `semantic`, `keyword` |
| `top_k` | 8 | 1–20 |
| `context_chunks` | 1 | 0–3 |
| `include_figures` | false | boolean |
| `max_searches` | 6 | 1–12 |
| `max_chunks` | 20 | 1–60 |
| `max_figure_images` | 4 | 0–20 |

Ask's LLM `search` tool also accepts `quality`: `strict` (keep hits at least
0.85 of the top score), `balanced` (0.55, default), or `permissive` (keep
all). Scores are RRF-based, not 0–1 cosine. If the cutoff would drop every
hit, the single best result is kept. Re-searches skip chunks already cited
in the conversation.

Chat **Trace** shows prompts, tool calls, and streamed answers. When an LLM
HTTP error includes `provider_error_detail`, Trace also expands **Provider
error details** on the error banner. Source loading remains independent of library inspection,
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
Explorer lists `.vera` and `.pdf` files up to 32 directory levels below a
library root (the root itself is depth 0). Deeper files are omitted from the
tree. The listing payload sets `truncated: true` when that cap is hit;
Explorer does not show a banner for it. A folder with no `.vera` files remains active and watched; Search and
Ask report that nothing is searchable until archives are present.

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

On Windows, packaging writes outside the repo (electron-builder rename locks
inside a watched checkout). The unpacked app is
`%LOCALAPPDATA%\Vera\desktop-release\win-unpacked\VERA.exe`. Override the
folder with `VERA_DIST_OUTPUT`.

Create the distributable Windows installer:

```bash
npm run app:release
```

This rebuilds the app and Python sidecar and writes `VERA Setup <version>.exe`
into `%LOCALAPPDATA%\Vera\desktop-release` (and clears any leftover
`packages/vera-app/release` directory).
Sidecar freeze vendors a VERA-exported MiniLM ONNX graph into gitignored
`packages/vera-app/build/` (later builds reuse that snapshot). Torch and
Sentence Transformers are excluded from the freeze.

## Plugins in the same environment

Source-run (`npm run app:dev`) and packaged builds use **one interpreter**.
Search, Ask, indexing, and PyMuPDF conversion all run in
the sidecar. Extra converters are pip packages in that environment, not a
second interpreter. The 0.3.0 sidecar does not run Docling conversion.

The packaged Windows installer freezes PyMuPDF, hashing, and ONNX Runtime
into `vera-sidecar.exe`. MiniLM
(`all-MiniLM-L6-v2`) ONNX weights ship inside Setup.exe, so **Local semantic
(MiniLM)** does not download those files on
first use. Docling / **Advanced layout (slower)** is not part of the 0.3.0
desktop app; install `vera-cli[docling]` and convert from the CLI. Hosted
embedding providers
(OpenAI, Voyage, Ollama) are a 0.3.1 follow-up.

CLI users who want Docling install it into the VERA environment:

```bash
pip install "vera-cli[docling]>=0.3.0"
# or from a checkout:
uv sync --extra docling
```

CLI Docling may download layout models into `DOCLING_ARTIFACTS_PATH`. That
pipeline is not listed in the 0.3.0 desktop Convert view.

Ingest plugins register under `vera.ingest_pipelines`; embedders register
under `vera.embedders`. Desktop Convert calls `preflight_embedder` before writing an
archive. MiniLM runs on ONNX Runtime in the Windows sidecar with a
VERA-exported, SHA256-pinned graph. `npm run app:dev` vendors that graph
into `packages/vera-app/build/minilm` before Electron starts (exporting
once with `--extra ml` if the snapshot is missing). It does not silently
fall back to Sentence Transformers when the `onnx` extra is installed.
Other Sentence Transformers models still need `uv sync --extra ml`. A missing
`onnxruntime` module in a checkout means that extra is not installed —
run `uv sync --extra onnx` (or `--extra app`) and restart the app. See
[Creating an ingest pipeline plugin](creating-an-ingest-pipeline.md) and
[Creating an embedding provider](creating-an-embedding-provider.md).
Convert and embed always run in-process in the sidecar; see
[Convert in one sidecar](desktop-app-architecture.md#convert-in-one-sidecar).

## Common startup problems

- **`uv` is not recognized** — install `uv`, open a new terminal, and rerun the
  command from the repository root.
- **`npm` is not recognized** — install Node.js, open a new terminal, and
  confirm `node --version` and `npm --version` work.
- **Electron dependencies are missing** — rerun `npm run app:install`.
- **The Electron window does not open** — check the `npm run app:dev` terminal
  for a Python sidecar, TypeScript, Vite, or port error before restarting it.
  If the sidecar fails to import numpy, PyMuPDF, or pdfplumber, point
  `VERA_APP_PYTHON` at the workspace `.venv` interpreter and restart.
- **Sidecar errors hide a Python traceback** — packaged IPC omits `traceback`
  unless `VERA_APP_DEBUG` is a truthy value. Source-run still prints
  `[vera-sidecar]` stderr.
- **`Failed to update Windows PE resources` / `uv-trampoline` Access denied** —
  Windows Defender or corporate EDR is locking uv's temporary launcher while
  uv installs a package that ships a console script. The sidecar build prefers
  the project virtualenv (`.venv`) and only falls back to `uv run`, so install
  PyInstaller once and rebuild:

  ```bash
  uv pip install "pyinstaller>=6"
  npm run app:dist
  ```

  Set `VERA_SIDECAR_PYTHON` or `VERA_APP_PYTHON` to use a different interpreter, or exclude the
  repository and `%TEMP%` from real-time scanning, then retry.
- **An extra parser or embedder is missing from Convert** — the 0.3.0 desktop
  sidecar ships PyMuPDF only. Docling is a CLI extra (`vera-cli[docling]`),
  not a Convert dropdown. For other plugins, install into
  the same environment the sidecar uses (`python -m pip install` or
  `python -m pip install -e <clone>`), then restart the app. Raw `PYTHONPATH`
  folders are not discovered. If Search warns that semantic groups were
  skipped, the embedder used at convert time is not available in this
  sidecar. Hosted embedders are not included until 0.3.1.

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
