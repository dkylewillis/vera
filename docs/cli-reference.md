# CLI reference

The `vera` console script and `python -m vera_cli` expose the same command
parser.

```text
vera convert
vera inspect
vera get
vera search
vera index build
vera index update
vera index status
vera validate
vera export
vera figures
vera eval
vera mcp
vera ocr-languages list
vera ocr-languages download
```

Run `vera COMMAND --help` for parser-generated usage. This page is the
human-oriented overview. The portable skill's
[exhaustive CLI contract](https://github.com/dkylewillis/vera/blob/main/skills/vera/references/cli-reference.md) documents
complete JSON object shapes, stdout/stderr behavior, exit codes, and filesystem
effects without duplicating that contract here.

## `vera convert INPUT [OUTPUT]`

Convert one PDF, Markdown file, or a directory of supported sources.

Options:

- `--model MODEL` (`hashing`; accepts `provider:model-id` specs such as
  `sentence-transformers:all-MiniLM-L6-v2` or `openai:text-embedding-3-small`;
  unknown providers exit with an
  error; MiniLM needs the `ml` extra, or the `onnx` extra plus an ONNX
  snapshot, other Sentence
  Transformers models need the `ml` extra, and the Windows installer vendors a
  VERA-exported MiniLM graph. MiniLM uses ONNX Runtime when a graph is present
  and Sentence Transformers otherwise. OpenAI embeddings ship with
  `vera-cli` as `vera-embed-openai`; set `OPENAI_API_KEY`. Archives converted
  with OpenAI are not portable for semantic search)
- `--parser PARSER` (omitted: choose from the file extension — PDF → `pymupdf`,
  Markdown → `markdown`; accepts `provider[:variant]` specs such as
  `docling` / `docling:hybrid` when `vera-cli[docling]` is installed; unknown
  providers exit with an error; the 0.3.x Windows installer does not include
  Docling)
- `--chunk-size N` (`500`; compatibility alias; PyMuPDF counts whitespace-split
  words, Docling counts whitespace tokens)
- `--overlap N` (`75`; compatibility alias; PyMuPDF counts whitespace-split
  words; forwarded only when the pipeline advertises overlap, e.g. PyMuPDF —
  not Docling; sliding-window chunking clamps overlap to `chunk_size - 1`)
- `--store-original VALUE` (`true`)
- `--ocr auto|off|force` (`auto`; compatibility alias)
- `--ocr-language CODE` (`eng`; Tesseract/PyMuPDF compatibility alias; not
  forwarded to Docling)
- `--ocr-dpi N` (`300`, must be positive; compatibility alias; PyMuPDF only)
- `--ocr-allow-download` (compatibility alias; PyMuPDF only; fetches missing
  `--ocr-language` Tesseract data from a curated, checksum-verified registry
  into a local cache instead of failing — see `vera ocr-languages`)
- `--pipeline-option KEY=VALUE` (repeatable; provider-owned options that
  override compatibility aliases for the same key)
- `--embedder-option KEY=VALUE` (repeatable; provider-owned embedding options
  forwarded to the selected embedding provider)
- `--recursive`
- `--overwrite`
- `--json`

Conversion selectively OCRs image-based low-text pages through PyMuPDF and
Tesseract, publishes a validated temporary archive atomically, and fails when
no searchable chunks are extracted. English language data is bundled for
offline, zero-setup OCR; other selected languages either require
`--ocr-allow-download` (or the equivalent `ocr_download` pipeline option) to
auto-fetch curated language data, or a manually installed Tesseract
`.traineddata` file with `TESSDATA_PREFIX` set. Directory conversion writes
archives beside source files, skips an existing `.vera` only when it validates and
its stored `source_file_hash` matches the current source file, reports malformed
outputs separately, and does not accept `OUTPUT`.
Pipeline-owned defaults and validation live in each ingest plugin; advertised
integer `minimum`/`maximum` bounds are enforced (for example `chunk_size`
100–3000). See [Convert documents](conversion.md#pipeline-options).
Embedding-provider options follow the same Options + descriptor pattern
(hashing `dimension` is 8–4096); see
[Creating an embedding provider](creating-an-embedding-provider.md).

## `vera inspect FILE`

Print archive metadata and summary counts, including archive size, creation
time, embedding dimensions and normalization policy, parser/chunking settings,
OCR diagnostics, and attachment count when recorded. Normalization is `l2`,
`none`, or `unknown`.

Options: `--json`. JSON includes `file` (the requested path) and `path` (the
opened archive).

## `vera get FILE CHUNK_ID`

Fetch one stored chunk by exact id from a single `.vera` archive. `CHUNK_ID`
is case-sensitive; there is no prefix match or directory/corpus lookup.

Options:

- `--json`
- `--figures`
- `--regions`

JSON is one object with `ok`, `file`, `path`, `chunk_id`, `text`, and the same
citation fields as a search hit (`page_start`, `page_end`, `heading_path`,
`source_filename`, `document_id`). It does not include `score`. `--figures` and
`--regions` add the same metadata shapes as `vera search`. An unknown or
whitespace-only id exits 1 with `{"ok": false, "error": "chunk not found: ..."}`.

## `vera search FILE_OR_DIRECTORY QUERY`

Search one archive or a directory as a corpus.

Options:

- `--mode semantic|keyword|hybrid` (`hybrid`)
- `--top-k N` (`10`)
- `--context-chunks N` (`0`)
- `--figures`
- `--regions`
- `--recursive`
- `--exclude PATTERN` (repeatable)
- `--json`

`--figures`, `--regions`, and context fields are exposed through JSON output.
Directory search JSON also includes `skipped_files` with paths and validation
reasons for malformed archives that were excluded. Indexed directory search
also includes `skipped_semantic_model_groups`; each entry identifies a model
name, indexed dimension, and loading or dimension error that prevented that
group from participating in semantic or hybrid retrieval. Non-JSON output
prints the same entries as warnings.

## `vera index build DIRECTORY`

Build a local collection index.

Options:

- `--recursive`
- `--exclude PATTERN` (repeatable)
- `--json`

Writes `.vera-index/` under the library root. Indexing uses a unique
temporary sibling; publication takes `.vera-index/build.lock`, then deletes
every other generation directory. An empty discovery set raises unstructured
`No .vera files found in ...` (exit 1, no JSON). JSON reports `invalid`
(validation or open failure) and `incompatible` (vector length ≠ declared
dimension) separately; those rows also appear on `index status` as
`skipped_files`. If no archive can be indexed, the command raises
`No valid .vera files could be indexed` on stderr and does not print JSON.

## `vera index update DIRECTORY`

Rebuild an existing index using its saved discovery settings.

Options: `--json`.

## `vera index status DIRECTORY`

Report whether an index exists and is fresh, including the paths, categories,
and reasons retained for files skipped by the active index. Existing-index
reports also include generation/build/check/verification timestamps, storage
sizes, source-versus-indexed chunk coverage, and per-model dimensions and
document/chunk counts.

Options: `--json`.

Exits 1 when the index is missing or stale while still emitting a report.

## `vera validate FILE`

Validate archive integrity and consistency.

Options: `--json`. JSON includes `file` (the requested path) and `path` (the
opened archive). Counts keys are `chunks`, `embeddings`, `fts_rows`, and
`attachments`.

Exits 1 when validation finds an issue while still emitting a report.

## `vera export FILE [OUTPUT]`

Write the embedded source document to its stored filename, a chosen path, or an
existing directory.

Options: `--json`.

## `vera figures FILE`

List stored figure attachments, or write their image files to a directory.

`FILE` is a single `.vera` archive.

Options:

- `--out-dir DIR` writes `{asset_id}.{ext}` files and adds `path` to JSON
- `--asset-id ID` limits to one attachment id (repeatable)
- `--page-start N` / `--page-end N` (1-based page filter)
- `--json`

Without `--out-dir` the JSON has `out_dir: null` and no `path` fields. Image
bytes are never included. A missing or non-figure `--asset-id` exits 1 with
`{"ok": false, "error": "..."}`.

## `vera eval FILE QUERIES`

Evaluate retrieval against expected pages or terms. `FILE` is a single
`.vera` archive; the command does not search a directory or collection index.

Options:

- `--mode semantic|keyword|hybrid|all` (`all`)
- `--top-k N` (`5`)
- `--json`

Exits 1 if any expected answer is missed while still emitting a report.

## `vera mcp`

Run the long-lived stdio MCP server. This command does not accept `--json`.
Install the `mcp` optional dependency first.

## `vera ocr-languages list [LANGUAGE]`

List Tesseract OCR language codes usable by the `pymupdf` parser: bundled
(ships with VERA, English only), cached (already downloaded), and
downloadable (in VERA's curated, checksum-verified registry of
`tesseract-ocr/tessdata_fast` codes). `LANGUAGE` optionally limits the report
to specific `+`-joined codes (e.g. `eng+fra`); omit it to list every known
code.

Options: `--json`.

Codes outside the curated registry are reported with `downloadable: false`
and need a manually installed `.traineddata` file plus `TESSDATA_PREFIX`.

## `vera ocr-languages download LANGUAGE`

Fetch one or more `+`-joined Tesseract language codes (e.g. `fra` or
`fra+deu`) into the local cache (override the location with
`VERA_TESSDATA_CACHE`), verifying each download's SHA-256 against VERA's
pinned registry before it is used. Already-cached codes are reused without a
network request. Exits 2 for a code with no bundled or registry data.

Options: `--json`.

## JSON and exit codes

One-shot commands support `--json` and print one JSON object on success.

Do not assume nonzero output is unstructured:

- `validate` returns a report when the archive is invalid;
- `index status` returns a report when the index is stale or missing;
- `eval` returns a report when a query misses;
- `export` returns an error object when no source is stored;
- `figures` returns an error object when a requested `--asset-id` is missing
  or is not a figure attachment;
- `get` returns an error object when the chunk id is missing from the archive;
- `convert` returns `{"ok": false, "error": "..."}` when extraction or
  validation fails, the input path is missing, or an OpenAI embedder fails
  (missing `OPENAI_API_KEY`, HTTP errors) (exit 1), or `--parser` /
  `--model` is unknown (exit 2). Directory conversion also prints a batch
  report and exits 1 when any file failed or an existing output was
  malformed;
- `ocr-languages download` returns `{"ok": false, "error": "..."}` and exits 2
  for an unknown or unregistered code;
- `mcp` prints an install hint and exits 2 when the optional `mcp` extra is
  not installed (this command does not accept `--json`).

Other path, dependency, and runtime failures generally write an unstructured
error or traceback to stderr. Check the exit status and command-specific
contract before parsing output.

## Shell quoting

Quote file paths and natural-language queries:

```bash
vera search "C:/My Documents/manual.vera" "parking requirements" --json
```

For multi-line commands, POSIX shells use `\` while PowerShell uses a backtick.
Single-line commands are portable across both.
