# Troubleshooting

## `vera` is not recognized

Verify the active Python environment:

```bash
python --version
python -m pip show vera-cli
python -m vera_cli --help
```

If module invocation works, the environment's scripts directory is not on
`PATH`. Activate the environment or continue using `python -m vera_cli`.

## A command cannot find a file

- Quote paths containing spaces.
- Confirm the path from the shell running VERA.
- Use an absolute path when a tool runs in another process, such as an MCP
  client.
- Remember that corpus search expects a directory containing `.vera` files,
  not PDFs.

## Directory search finds no archives

A directory search is non-recursive by default:

```bash
vera search "./library" "query" --recursive
```

Check that exclusion patterns do not remove every archive. Directory symlinks
and archive symlinks are intentionally not followed.

## Search returns no useful results

Try, in order:

1. shorten the query to topic plus action;
2. use hybrid mode;
3. use keyword mode for exact document terminology;
4. use semantic mode for paraphrased language;
5. try a synonym or parent concept;
6. increase `--top-k`;
7. add `--context-chunks 1` to interpret a promising hit.

An empty successful result does not prove the topic is absent. See
[Search documents](searching.md). Desktop Ask additionally filters hits with
a relative `quality` cutoff and skips already-cited chunks; try **permissive**
quality, another mode, or the Search view when Chat returns too little
evidence.

## Exact identifiers produce broad matches

Keyword fallback can strip punctuation and create prefix terms. For a short
code such as `EL-A`:

```bash
vera search "manual.vera" "EL-A zoning district" --mode keyword --top-k 10 --json
```

Confirm that the literal identifier appears in result text before reporting a
match.

## A neural-model archive fails to search

Archives record the embedding model used during conversion. Search must load
that same provider to embed the query. Install the `ml` extra for any Sentence
Transformers archive, including MiniLM:

```bash
python -m pip install "vera-doc[ml]"
```

MiniLM (`all-MiniLM-L6-v2`) prefers ONNX Runtime when a VERA-exported graph is
available and falls back to Sentence Transformers otherwise, so `vera-doc[ml]`
is enough on the CLI. `vera-doc[onnx]` avoids the Torch dependency but needs a
graph via `VERA_ONNX_MINILM_HOME`; the packaged desktop app ships both. The
default hashing model does not require any extra.

Unknown model or provider names raise `UnknownEmbeddingModelError` at convert
time and never create hashing vectors under a different name. If a custom name
was used accidentally, reconvert with `--model hashing` or a supported
`provider:model-id` spec.

A broken `vera.embedders` entry point is recorded during registry scan. Inspect
it with `from vera_doc.embeddings import list_embedder_load_errors` (not
exported from `vera_doc`). Failed plugins are not retried until
`reset_embedding_registry()` runs. `UnknownEmbeddingModelError` then includes
`Plugin load errors:` with the provider, kind, and exception.

An archive already written with a model that is not installed in the current
environment cannot be searched semantically until that provider is available.
Indexed directory search still returns keyword hits and reports the omitted
group in `skipped_semantic_model_groups`.

## Ask returns too little evidence

Desktop Ask filters search hits with a relative `quality` cutoff (`strict`
0.85, `balanced` 0.55, `permissive` keep-all) and skips already-cited chunks.
Switch the Chat mode, ask the model to retry at `permissive`, or use the
Search view (no quality filter). Custom modes live in `userData/modes`; use
**Reload modes** after editing. For LLM HTTP failures, enable Chat **Trace**
to expand **Provider error details** (`provider_error_detail`).

## Validation fails because the original is missing

An archive created with:

```bash
vera convert "input.pdf" --store-original false
```

is searchable but does not contain the source PDF. The current validator
reports this as a **warning**, and export is unavailable. Reconvert with the default
`--store-original true` if source preservation is required.

## Export reports that no source is stored

The archive was created without the original document or is damaged. Export
cannot reconstruct the PDF from parsed text. Locate the source PDF and
reconvert it. In the desktop app, right-click the `.vera` file and choose
**Reconvert…** when the original PDF is beside the archive or stored inside it.

If Reconvert shows **Could not read archive metadata**, inspect failed and no
sibling PDF was listed, so the app does not export an embedded original.
Place the matching `.pdf` next to the archive, or open Document Info and
export the original once the archive is readable.

## Explorer is missing nested files

The desktop Explorer lists `.vera`, `.pdf`, and `.md` / `.markdown` files up
to 32 directory levels below a library root. Files deeper than that are
omitted from the tree; the listing payload sets `truncated: true`, but
Explorer does not show a banner for that cap. Flatten the folder layout or
open the nested directory as its own library. Office and HTML sources
(`.docx`, `.pptx`, `.xlsx`, `.html`, `.htm`) are not listed — convert those
with the CLI Docling extra, then search the resulting `.vera`.

## A collection index is stale

Check status:

```bash
vera index status "./library" --json
```

This command exits 1 when stale or missing while still returning a JSON report.
`vera index status` hashes every indexed archive (`verify_hashes` defaults to
true; `verified_at` is set). Directory search and the desktop index badge use
size and mtime only (`verify_hashes=false`; `verified_at` is null), so a
same-size, same-mtime byte change is not stale until you run `index status` or
desktop **Inspect** (that library refresh passes `verify_hashes=true`).
Rebuild with saved settings:

```bash
vera index update "./library" --json
```

Search remains available through direct-file fallback while the index is
stale. A successful rebuild deletes every other generation directory; do not
rely on `.vera-index/generations/` as a rollback history.

## Index skipped files as invalid or incompatible

A successful index can still omit archives. `vera index build` / `update`
JSON lists them in separate `invalid` and `incompatible` arrays; `vera index
status --json` repeats them in `skipped_files` with a `category` of
`invalid` or `incompatible`.

- `invalid`: validation failed, or opening/indexing raised (corrupt SQLite,
  missing tables, unreadable file).
- `incompatible`: a chunk vector length does not match the archive's declared
  embedding dimension. The archive can still validate and search on its own;
  it is omitted from the library matrix so mixed-model search stays aligned.

Those skipped rows do not make an otherwise valid index stale. Directory
search JSON copies a fresh index's skips into top-level `skipped_files`
(absolute paths). The nested `index` object is the full status report, so
`index.skipped_files` uses the same relative paths as `index status`. Direct
fallback search (stale or missing index) does not reuse those categories; it
reopens archives and records new skips as `invalid`.

## Index build finds no archives

`vera index build` raises unstructured `No .vera files found in ...` (exit 1,
no JSON) when discovery returns nothing. Pass `--recursive` for nested
libraries. Parallel builds of the same root may index at the same time;
publication serializes on `.vera-index/build.lock`, and the last successful
publish wins.

## Index build finds no valid archives

If every discovered `.vera` is skipped, `vera index build` raises
`No valid .vera files could be indexed` and exits 1. `--json` does not emit a
report for this failure (it is an uncaught `ValueError` on stderr). Validate
or reconvert the archives, then rebuild.

## Index update says no index exists

Build it first:

```bash
vera index build "./library" --recursive --json
```

`index update` only works when saved index configuration already exists.

## Conversion skips files

Directory conversion skips an existing same-named `.vera` only when it
validates and its stored `source_file_hash` matches the current source file
(PDF, Markdown, or Office/HTML). Changed sources and archives with a missing
or unreadable hash are reconverted. Review `skipped_existing` for unchanged
skips and `malformed_existing` for archives that must be repaired or replaced.
Use `--overwrite` only when replacement is intentional:

```bash
vera convert "./sources" --recursive --overwrite --json
```

## Conversion says a PDF requires OCR

VERA rejects a conversion when the parser extracts no searchable chunks. This
commonly means the PDF contains scanned page images without a text layer.
Automatic English OCR should recognize image-based prose pages without a
separate installation because VERA bundles the `eng` model. Retry explicitly
to expose OCR errors:

```bash
vera convert "scan.pdf" "scan.vera" --ocr force --ocr-language eng --ocr-dpi 300
```

Equivalent provider-owned form:

```bash
vera convert "scan.pdf" "scan.vera" \
  --pipeline-option ocr_mode=force \
  --pipeline-option ocr_language=eng \
  --pipeline-option ocr_dpi=300
```

If an English error says the bundled model is missing, reinstall VERA.

Languages other than `eng` are not bundled. Prefer the curated download
workflow:

```bash
vera ocr-languages list --json
vera ocr-languages download fra --json
vera convert "scan.pdf" "scan.vera" --ocr-language fra
```

`--ocr-allow-download` fetches the same checksum-verified registry during
convert. Override the cache with `VERA_TESSDATA_CACHE` (default
`~/.cache/vera/tessdata` on Linux, `%LOCALAPPDATA%\vera\tessdata` on Windows).
Codes outside the registry still need a manually installed `.traineddata` file
and `TESSDATA_PREFIX`. `--ocr-language` accepts Tesseract codes such as `deu`
or `eng+spa`.

An OCR pass can still produce no searchable text when the scan is blank,
low-resolution, handwritten, or mostly diagrams. VERA's selective OCR targets
prose and does not reconstruct scanned tables, forms, or complex multi-column
layouts. Preprocess those files with a layout-aware OCR tool before converting.
A failed conversion does not replace an existing destination and removes its
temporary output.

Scanned pages that still have a native header, Bates stamp, or letterhead are
OCR'd in auto mode: a large-image page with fewer than 200 alphanumeric
characters is treated as sparse native text, not a searchable text page. Use
`--ocr force` only when you need to replace native extraction on every page.

## Conversion fails for a parser name

`--parser` must name an installed ingest pipeline (`provider[:variant]`). The
default provider is `pymupdf` (from `vera-ingest-pymupdf`):

```bash
vera convert "input.pdf" --parser pymupdf
```

For Docling, install the official extra and convert from the CLI. The 0.3.0
desktop app does not list Advanced layout:

```bash
pip install "vera-cli[docling]>=0.3.0"
# or from a checkout:
uv sync --extra docling
vera convert "input.pdf" --parser docling
vera convert "memo.docx" --parser docling
vera convert "notes.html"
```

Unknown names fail before parsing and never fall back to another pipeline.

The desktop app uses one sidecar interpreter. Install extra pip plugins into
the same environment (`python -m pip install` or `python -m pip install -e
<clone>`), then restart the app. Raw `PYTHONPATH` folders are not discovered.
If Search reports skipped semantic model groups, the convert-time embedder is
not available in this sidecar. OpenAI embeddings are bundled (`OPENAI_API_KEY`
under **File > Settings → Embeddings**); Voyage and Ollama are not. A
source-run or CLI convert that fails with
`No module named 'onnxruntime'` needs `uv sync --extra onnx` in the
environment that runs VERA. Other Sentence Transformers models still need
`uv sync --extra ml`. The packaged Windows sidecar already includes
ONNX Runtime and MiniLM weights.

A plugin can be installed and still missing from Convert. Broken
`vera.ingest_pipelines` entry points are logged as warnings and omitted from
`list_ingest_pipelines()`; inspect them with
`list_ingest_pipeline_load_errors()`. Broken `vera.embedders` entry points
surface as `Plugin load errors:` on `UnknownEmbeddingModelError`.

If Hugging Face Hub downloads warn about unauthenticated requests or hit rate
limits, set `HF_TOKEN` (see `.env.example`) or save a token under **File >
Settings → Hugging Face** in the desktop app.

If a CLI Docling convert is slow or sits on model download, check stderr for
timing lines such as
`2026-08-19T20:44:01.123Z timing step=import_docling elapsed_ms=12450`.
Set `DOCLING_ARTIFACTS_PATH` for a local layout-model cache. The desktop
convert log (**File > Open convert log...**, Convert **Open log**, or
**Settings → Diagnostics**) records PyMuPDF convert timing in
`userData/logs/sidecar.log` for `app:dev` and packaged VERA. CLI `vera convert`
prints the same timing on stderr without writing that desktop file. Each step
also logs a
start line (no `elapsed_ms`) so a long `resolve_pipeline` or MiniLM load is
visible while it is still running.

## Convert stays on Discovering files

Convert reports **Discovering files…** until MiniLM is resolved. Check
`sidecar.log` for `resolve_embedder` timing. MiniLM no longer imports Torch
at sidecar start. Sidecar stderr `MiniLM runtime=onnx` means ONNX Runtime is
in use. `Loading weights: 0/103` is Hugging Face safetensors via Sentence
Transformers — that MiniLM path is used only when the `onnx` extra is not
installed. `npm run app:dev` vendors the ONNX graph first; a missing graph
with the `onnx` extra installed is an error, not a silent Sentence
Transformers load.

## Figures are missing or have no caption

- Search with `--figures --json`; figure metadata is not shown in ordinary text
  output.
- Search the caption wording and the subject.
- Some PDF tables are text blocks rather than image assets.
- Captions are linked by page layout and proximity and may be `null`.

## Highlight boxes cover extra text

Regions are block-granular, not word-precise. A chunk that starts or ends
inside a layout block maps to the whole block. This is expected behavior.

## Loading source timed out

The desktop viewer copies the original source into a local cache before PDF.js
or the Markdown preview can render it. Large stormwater manuals can take a while on first open. VERA
now prefers a sibling `manual.pdf` next to `manual.vera` and reuses a cache
file on later opens instead of extracting and re-hashing the embedded
original. If the load still exceeds five minutes, cancel it from the viewer
close control and keep the matching PDF beside the archive.

## `--where` returns no hits

`--where` is exact equality on top-level stored keys, applied before `top_k`.
A missing key fails the predicate. Values coerce like `--pipeline-option`
(digit-only integers, `true`/`false`/`yes`/`no`/`on`/`off` booleans, otherwise
strings; dotted tokens such as `3.10` stay strings). CLI `--metadata year=2024`
and `--where year=2024` both become ints and match; a Python tag stored as
the string `"2024"` does not match `--where year=2024`. List-valued *stored*
metadata is not an IN clause — IN applies only to the filter value
(`--where company=GRID,PWRX`). Empty comma tokens exit 2. Desktop Search and
Ask have no `--where` control; use the CLI or MCP.

## Search skips a semantic model group

Indexed hybrid or semantic search can return keyword hits while omitting one
embedding space. Inspect `skipped_semantic_model_groups` in the JSON report
(or the `Warning: skipped semantic model group` lines in text output). Each
entry names the model, indexed dimension, and load or dimension error.

Install the missing provider in the process that embeds the query (CLI
environment or desktop sidecar). Keyword results from
the same search remain usable. OpenAI archives need `OPENAI_API_KEY` at search
time as well; keyword hits still work without it. Voyage and Ollama are not
bundled.

## vera-lab cannot open an archive

`vera-lab` is a contributor tool (workspace `dev` extra), not part of the
shipped CLI. Archive mode rasterizes the embedded source PDF. Archives created
with `--store-original false` fail with "Original source document is not stored
in this archive". Reconvert with the default `--store-original true`, or run
the lab against the source PDF instead.

`--parser` is ignored for `.vera` inputs; it only selects live pipelines when
the source is a PDF. Live mode does not write embeddings or an archive.
Success prints the HTML path; failures print `vera-lab: ...` to stderr and
exit 1.

## JSON parsing fails on a nonzero exit

Check the command:

- `validate`, `index status`, `eval`, and failed `export` can return structured
  JSON with exit status 1;
- `convert --json` returns `{"ok": false, "error": "..."}` for extraction or
  validation failure, a missing input path, and OpenAI embedder failures such
  as a missing `OPENAI_API_KEY` (exit 1), and for an unknown `--parser` /
  `--model` (exit 2); directory conversion prints a batch report
  and exits 1 when any file failed or an existing output was malformed;
- `ocr-languages download` returns structured JSON with exit status 2 for an
  unknown or unregistered code;
- most other path, dependency, and runtime failures write unstructured errors
  to stderr.

Do not parse stderr as JSON. See the [CLI reference](cli-reference.md).

## Sidecar errors omit a Python traceback

Packaged desktop IPC error responses include `error` but omit Python
`traceback` unless `VERA_APP_DEBUG` is a truthy value (`1`, `true`, `yes`,
or `on`). Source-run (`npm run app:dev`) still prints sidecar stderr as
`[vera-sidecar]` lines. Set `VERA_APP_PYTHON` to the workspace `.venv`
interpreter when the sidecar fails to import numpy, PyMuPDF, or pdfplumber.

## MCP does not start

Install the optional dependency:

```bash
python -m pip install "vera-cli[mcp]"
```

Install the extra, not a bare `mcp` package. `vera-mcp` requires `mcp>=1.0,<2`
because SDK 2.x removed `mcp.server.fastmcp`.

Ensure the MCP client launches the command from that environment. See
[MCP integration](mcp.md).

## Repository test command fails on Windows

From an initialized checkout, prefer:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\ -q
```

On a fresh machine:

```bash
uv sync --extra dev --extra onnx --extra ml --extra app --extra mcp
uv run --extra dev python -m pytest -q
```

## Reporting a problem

Include:

- operating system and Python version;
- VERA package version;
- the command and exit status;
- stderr and JSON report, if any;
- `vera inspect FILE --json` output when safe to share;
- whether the archive uses hashing or a neural embedding model.

Do not attach confidential source documents or `.vera` archives to a public
issue without reviewing their contents.
