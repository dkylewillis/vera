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
that same provider to embed the query. Install the optional machine-learning
dependency when the archive used Sentence Transformers:

```bash
python -m pip install "vera-doc[ml]"
```

The required Sentence Transformers model may also need to be available in the
runtime environment. The packaged desktop app already includes
`sentence_transformers` and `all-MiniLM-L6-v2` weights. The default hashing
model does not require this extra.

Unknown model or provider names raise `UnknownEmbeddingModelError` at convert
time and never create hashing vectors under a different name. If a custom name
was used accidentally, reconvert with `--model hashing` or a supported
`provider:model-id` spec.

A broken `vera.embedders` entry point is recorded during registry scan. Inspect
it with `from vera_doc.embeddings import list_embedder_load_errors` (not
exported from `vera_doc`). Failed plugins are not retried until
`reset_embedding_registry()` runs.

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

The desktop Explorer lists `.vera` and `.pdf` files up to 32 directory
levels below a library root. Files deeper than that are omitted from the
tree. Flatten the folder layout or open the nested directory as its own
library.

## A collection index is stale

Check status:

```bash
vera index status "./library" --json
```

This command exits 1 when stale or missing while still returning a JSON report.
Rebuild with saved settings:

```bash
vera index update "./library" --json
```

Search remains available through direct-file fallback while the index is
stale. A successful rebuild deletes every other generation directory; do not
rely on `.vera-index/generations/` as a rollback history.

## Index build finds no archives

`vera index build` raises unstructured `No .vera files found in ...` (exit 1,
no JSON) when discovery returns nothing. Pass `--recursive` for nested
libraries. Parallel builds of the same root may index at the same time;
publication serializes on `.vera-index/build.lock`, and the last successful
publish wins.

## Index update says no index exists

Build it first:

```bash
vera index build "./library" --recursive --json
```

`index update` only works when saved index configuration already exists.

## Conversion skips files

Directory conversion skips an existing same-named `.vera` only when it
validates and its stored `source_file_hash` matches the current PDF.
Changed PDFs and archives with a missing or unreadable hash are reconverted.
Review `skipped_existing` for unchanged skips and
`malformed_existing` for archives that must be repaired or replaced. Use
`--overwrite` only when replacement is intentional:

```bash
vera convert "./pdfs" --recursive --overwrite --json
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

For Docling, install the official extra (CLI) or use Advanced layout in the
desktop app (already bundled):

```bash
pip install "vera-cli[docling]>=0.3.0"
# or from a checkout:
uv sync --extra docling
vera convert "input.pdf" --parser docling
```

Unknown names fail before parsing and never fall back to another pipeline.

The desktop app uses one sidecar interpreter. Install extra pip plugins into
the same environment (`python -m pip install` or `python -m pip install -e
<clone>`), then restart the app. Raw `PYTHONPATH` folders are not discovered.
If Search reports skipped semantic model groups, the convert-time embedder is
not available in this sidecar. Hosted embedders are a 0.3.1 follow-up. A
A source-run or CLI convert that fails with
`No module named 'sentence_transformers'` needs `uv sync --extra ml` in the
environment that runs VERA. The packaged Windows sidecar already includes
that module and MiniLM weights.

If Hugging Face Hub downloads warn about unauthenticated requests or hit rate
limits, set `HF_TOKEN` (see `.env.example`) or save a token under **File >
Settings → Hugging Face** in the desktop app.

If **Advanced layout** looks stuck in `npm run app:dev` with no sidecar
lines, the prefetch is still running: Hugging Face Xet used to transfer
170–210 MB files with a file-count bar that did not move, and tqdm `\r`
updates overwrote the PowerShell line. Restart after this build to see
`[vera-sidecar]` byte progress and a 15-second cache-size heartbeat. The
Windows `app:dev` cache is `%APPDATA%\@vera\app\docling-artifacts`. When Heron ONNX
(`model.onnx`) and TableFormer accurate (`tm_config.json`) are already there,
Convert skips the Hub download and only loads those weights. Packaged Setup.exe
already includes those snapshots.

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

The desktop viewer copies the original PDF into a local cache before PDF.js
can render it. Large stormwater manuals can take a while on first open. VERA
now prefers a sibling `manual.pdf` next to `manual.vera` and reuses a cache
file on later opens instead of extracting and re-hashing the embedded
original. If the load still exceeds five minutes, cancel it from the viewer
close control and keep the matching PDF beside the archive.

## Search skips a semantic model group

Indexed hybrid or semantic search can return keyword hits while omitting one
embedding space. Inspect `skipped_semantic_model_groups` in the JSON report
(or the `Warning: skipped semantic model group` lines in text output). Each
entry names the model, indexed dimension, and load or dimension error.

Install the missing provider in the process that embeds the query (CLI
environment or desktop sidecar). Keyword results from
the same search remain usable. Hosted embedding providers are not included
until 0.3.1.

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
- `ocr-languages download` returns structured JSON with exit status 2 for an
  unknown or unregistered code;
- most path, dependency, and runtime failures write unstructured errors to
  stderr.

Do not parse stderr as JSON. See the [CLI reference](cli-reference.md).

## MCP does not start

Install the optional dependency:

```bash
python -m pip install "vera-cli[mcp]"
```

Ensure the MCP client launches the command from that environment. See
[MCP integration](mcp.md).

## Repository test command fails on Windows

From an initialized checkout, prefer:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\ -q
```

On a fresh machine:

```bash
uv sync --extra dev --extra ml --extra app --extra mcp
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
