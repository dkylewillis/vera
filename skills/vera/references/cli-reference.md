# VERA CLI reference for agents

This reference describes the current `vera-cli` command contract. The
console entry point is `vera`; `python -m vera_cli` invokes the same parser.

## Runtime and installation

- Python: 3.10 or newer.
- Published CLI: `pip install "vera-cli>=0.3.1"`.
- Neural MiniLM embeddings require the `onnx` extra from `vera-doc`.
  Other Sentence Transformers models require the `ml` extra.
- `vera mcp` requires `pip install "vera-cli[mcp]>=0.3.1"` or
  `pip install "vera-mcp>=0.3.1"`.
- A repository checkout can use:
  `uv sync --extra dev --extra onnx --extra ml --extra app --extra mcp`.

Check `vera --help` first. If it is not on `PATH`, try
`python -m vera_cli --help`.

## Command inventory

### `vera convert INPUT [OUTPUT]`

Convert one PDF, Markdown, Office/HTML (Docling extra), or a directory of supported sources. CLI convert resolves the embedder with
`get_embedder` and does not call `preflight_embedder`; missing credential env
vars surface when the factory runs. Desktop Convert still gates on
`preflight_embedder`.

Options:

- `--model MODEL` defaults to `hashing`. Accepts `provider:model-id` specs
  (for example `hashing:vera-hashing-384` or
  `sentence-transformers:all-MiniLM-L6-v2`) plus legacy aliases
  (`hashing`, `vera-hashing-384`, `all-MiniLM-L6-v2`,
  `sentence-transformers/...`). Unknown providers raise and the command
  exits non-zero instead of silently falling back to hashing. CLI and
  source-run installs need the `ml` extra for MiniLM, or the `onnx` extra
  (ONNX Runtime) plus a
  MiniLM ONNX snapshot (`VERA_ONNX_MINILM_HOME` or the `app:dev` vendor path).
  MiniLM uses ONNX Runtime when a snapshot is present and Sentence
  Transformers otherwise. Other Sentence Transformers models need the `ml` extra. The
  Windows desktop installer vendors a VERA-exported `all-MiniLM-L6-v2` ONNX
  graph. Archive identity stays `sentence-transformers/all-MiniLM-L6-v2`.
  OpenAI embeddings ship with `vera-cli` as `vera-embed-openai`
  (`openai:text-embedding-3-small` / `-large`); set `OPENAI_API_KEY`. Archives
  converted with OpenAI are not portable for semantic search. Voyage and
  Ollama are not bundled.
- `--parser PARSER` omitted chooses an installed pipeline from the file
  extension (`pdf` → `pymupdf`, `md`/`markdown` → `markdown`, `docx`/`pptx`/
  `xlsx`/`html`/`htm` → `docling` when `vera-ingest-docling` is installed). Accepts ingest
  pipeline specs `provider[:variant]` (requires `vera-ingest-pymupdf` for
  PDFs; for example `docling` or `docling:hybrid` when `vera-ingest-docling`
  is installed). An explicit parser that does not advertise the file's
  extension exits with an error; there is no silent fallback. Unknown
  providers exit with a non-zero status and an
  install-the-plugin message. First **PDF** Docling
  convert may download layout and table models into `DOCLING_ARTIFACTS_PATH`
  (or Hugging Face Hub; about 380 MB: Heron ONNX + TableFormer accurate).
  Office/HTML Docling convert does not download those PDF layout models.
  The 0.3.0 desktop app does not list or freeze this pipeline; use
  `vera-cli[docling]`. An incomplete cache resumes instead of failing
  offline. Stopping mid-download does not abort Hugging Face immediately.
- `--chunk-size N`. Compatibility alias; omitted uses the selected pipeline's
  default. Forwarded only when the selected pipeline advertises a `chunk_size`
  field. PyMuPDF counts whitespace-split words; Docling counts whitespace
  tokens (not LLM subword tokens).
- `--overlap N`. Compatibility alias; omitted uses the selected pipeline's
  default. Forwarded only when the pipeline advertises `overlap` (PyMuPDF,
  also whitespace-split words). Docling does not receive overlap.
  Sliding-window chunking clamps overlap to `chunk_size - 1` so carry never
  overruns.
- `--store-original VALUE` defaults to `true`. Values `1`, `true`, `yes`, `y`,
  and `on` are true; `0`, `false`, `no`, `n`, `off`, and empty are false
  (case-insensitive). Any other token is rejected.
- `--ocr auto|off|force`. Compatibility alias for `ocr_mode`; omitted uses
  the selected pipeline's default. Automatic mode OCRs only image-dominant
  low-text pages.
- `--ocr-language CODE`. Compatibility alias; omitted uses the selected
  pipeline's default. Forwarded only when the selected pipeline's OCR engine
  is Tesseract (PyMuPDF). Docling/RapidOCR does not receive this alias and
  keeps its own default `en` unless you pass `--pipeline-option ocr_language=`
  with a RapidOCR-native code (`en`, `fr`, `cyrillic`, ...). `eng` is not
  valid for Docling.
- `--ocr-dpi N` must be positive. Compatibility alias; omitted uses the
  selected pipeline's default. Forwarded only when the pipeline advertises
  `ocr_dpi` (PyMuPDF). Docling does not receive DPI.
- `--ocr-allow-download` defaults to off. Compatibility alias for
  `ocr_download` (PyMuPDF only). When set, missing `--ocr-language` data is
  fetched from VERA's curated, checksum-verified registry (a subset of
  `tesseract-ocr/tessdata_fast`) into a local cache instead of raising;
  unaffected languages and the default `eng` path never touch the network.
  See `vera ocr-languages list` for the registry and `vera ocr-languages
  download` to pre-fetch outside a conversion.
- `--pipeline-option KEY=VALUE` is repeatable. Sets provider-owned
  `pipeline_options` entries (for example `--pipeline-option chunk_size=900`).
  Digit-only tokens become ints and `true`/`false`/`yes`/`no`/`on`/`off`
  become bools; dotted tokens such as `3.10` or `ocr_language=1.0` stay
  strings (they are not passed through `float()`). Typed `from_mapping`
  validation then checks each key, so `ocr_download=1` is usable.
  Explicit `--pipeline-option` values always override compatibility aliases
  for the same key.
- `--embedder-option KEY=VALUE` is repeatable. Sets provider-owned
  `embedder_options` entries (for example `--embedder-option batch_size=64`
  or `--embedder-option dimension=256`). Values coerce the same way as
  `--pipeline-option`.
- `--metadata KEY=VALUE` is repeatable. Stamps the same keys onto archive
  metadata and every chunk so `--where` can filter before `top_k`. Values
  coerce like `--pipeline-option`. Nested JSON is rejected. Reserved keys
  (`page_start`, `page_end`, `heading_path`, `source_filename`, `document_id`,
  `token_count`, `regions`, required format header keys, `default_embedding_*`,
  `_vera_*`, and convert-owned fields such as `source_file_hash`) exit 2.
  `title` may be overridden. Directory convert applies the same tags to every
  output; hash-matched skips do not restamp.
- `--recursive` recursively discovers supported source files in directory
  mode (PDF, Markdown, and Office/HTML when Docling is installed).
- `--overwrite` replaces existing outputs in directory mode. Without it,
  a sibling `.vera` is skipped only when it validates and its stored
  `source_file_hash` matches the current source file.
- `--json` emits one JSON object.

Each pipeline owns typed defaults and validation. Advertised integer
`minimum`/`maximum` bounds are enforced (`chunk_size` 100–3000; hashing
`dimension` 8–4096). PyMuPDF defaults:
`chunk_size=500` whitespace-split words, `overlap=75` words, `ocr_mode=auto`,
`ocr_language=eng`, `ocr_dpi=300`, `ocr_download=false`. Markdown defaults:
`chunk_size=500` words, `overlap=75` words (OCR keys are ignored so a mixed
PDF+Markdown directory convert can reuse one `pipeline_options` bag). Docling defaults:
`chunk_size=500` whitespace tokens, `ocr_mode=auto`, `ocr_language=en`,
`pdf_backend=docling_parse`
(no overlap/DPI/download fields; auto page recovery / `pypdfium2` fallback on
memory errors, then page-batch `pypdfium2` if the whole-document convert raises).

For a single PDF, omitted `OUTPUT` defaults to the input basename with a
`.vera` suffix. Conversion writes and validates a temporary sibling before
atomically replacing the output. A failure preserves an existing destination
and removes the temporary file. OCR uses the `vera-ingest-pymupdf` package
(PyMuPDF's local Tesseract integration with bundled English language data).
Other selected languages either require
`--ocr-allow-download` to auto-fetch curated data on demand, or a manually
installed Tesseract `.traineddata` file with `TESSDATA_PREFIX` set — the error
raised for a missing language explains which applies. PDFs that yield no
searchable chunks after OCR fail with an OCR-specific message. OCR targets
scanned prose; it does not reconstruct scanned tables or complex page layouts.
For a directory, outputs are written beside their source files. Supplying
`OUTPUT` with a directory is an error.

Single-file JSON:

```json
{
  "ok": true,
  "output": "C:/docs/manual.vera"
}
```

Empty-OCR, missing input, validation failure, or OpenAI embedder failure
(missing `OPENAI_API_KEY`, HTTP errors) with `--json`:

```json
{
  "ok": false,
  "error": "No searchable text or chunks were extracted; the PDF may be scanned and requires OCR."
}
```

Exit 1. `FileNotFoundError` and `OpenAIEmbedderError` use the same `{ok, error}`
object. Without `--json`, the message is printed to stderr. Unknown `--parser` /
`--model` uses the same JSON object and exits 2.

Directory JSON:

```json
{
  "ok": false,
  "directory": "C:/docs",
  "recursive": true,
  "overwrite": false,
  "discovered": 4,
  "converted": 2,
  "skipped": 1,
  "user_skipped": 0,
  "malformed": 1,
  "failed": 0,
  "outputs": ["C:/docs/a.vera", "C:/docs/nested/b.vera"],
  "skipped_existing": ["C:/docs/c.vera"],
  "skipped_by_user": [],
  "malformed_existing": [
    {
      "input": "C:/docs/d.pdf",
      "output": "C:/docs/d.vera",
      "issues": ["Missing required table: vera_metadata"]
    }
  ],
  "errors": []
}
```

Existing outputs are validated: only valid archives whose stored
`source_file_hash` matches the current source file appear in `skipped_existing`.
Changed sources and archives with a missing or unreadable hash are reconverted.
Invalid archives appear in `malformed_existing`.
`skipped_by_user` / `user_skipped` are reserved for interactive skip
requests (desktop app); CLI runs leave them empty. Each error entry has
`input` and `error`. A conversion failure or malformed existing output
sets `ok` false, prints the report, and exits 1. Supplying a directory
and an output path prints an error to stderr and exits 2.

### `vera inspect FILE`

Options: `--json`.

JSON combines the archive metadata with summary counts. `file` is the
requested path; `path` is the opened archive. Metadata is extensible, so
agents must tolerate additional keys.

```json
{
  "file": "manual.vera",
  "path": "C:/docs/manual.vera",
  "format_name": "VERA",
  "format_version": "0.2",
  "created_at": "2026-01-01T00:00:00+00:00",
  "title": "manual",
  "source_file_name": "manual.pdf",
  "default_embedding_model": "hashing",
  "default_embedding_dimension": 384,
  "default_embedding_normalization": "l2",
  "parser_name": "pymupdf",
  "parser_version": "pymupdf",
  "chunking_strategy": "heading_block_sliding_window:500:75",
  "ocr": {
    "ocr_engine": "tesseract",
    "ocr_mode": "auto",
    "ocr_language": "eng",
    "ocr_dpi": 300,
    "ocr_pages": []
  },
  "archive_size_bytes": 2457600,
  "source": "manual.pdf",
  "pages": 120,
  "chunks": 480,
  "attachments": 3
}
```

Metadata is extensible. `default_embedding_normalization` is `l2`, `none`, or
`unknown`; archives created before this field was introduced report `unknown`.
Summary counts, embedding dimensions, attachment counts, and
`archive_size_bytes` are integers.

### `vera get FILE CHUNK_ID`

Fetch one stored chunk by exact `chunks.chunk_id`. `FILE` is a single `.vera`
archive, not a directory. `CHUNK_ID` is case-sensitive with no glob or prefix
match. This command does not write files.

Options:

- `--json` emits one JSON object.
- `--figures` adds figure metadata/captions (same shape as `vera search
  --figures`; metadata only, not pixels).
- `--regions` adds highlight regions (same shape as `vera search --regions`).

Success JSON (exit 0):

```json
{
  "ok": true,
  "file": "manual.vera",
  "path": "C:/docs/manual.vera",
  "chunk_id": "chunk_0042",
  "text": "Detention shall be provided...",
  "page_start": 117,
  "page_end": 117,
  "heading_path": "Chapter 4 > Detention Design",
  "source_filename": "manual.pdf",
  "document_id": "document_0001"
}
```

`file` is the requested path; `path` is the opened archive. `chunk_id` and
`text` are always present; `text` is the stored chunk body, not a snippet.
Citation fields come from chunk metadata and may be `null` when the
extractor did not set them. Other metadata keys may appear at the top level
(search already does this). Do not expect `score`, `semantic_score`,
`keyword_score`, or the embedding vector. `--figures` / `--regions` add
`figures` / `regions` only when requested.

An unknown id, or a whitespace-only `CHUNK_ID` (rejected before the archive is
opened), exits 1 with structured JSON and no traceback:

```json
{
  "ok": false,
  "error": "chunk not found: chunk_zzzz"
}
```

Without `--json`, the same `chunk not found: ...` message is printed to
stderr. A missing path or a directory target follows `inspect`: unstructured
`FileNotFoundError` traceback on stderr, exit 1. Do not treat a directory as a
corpus scan.

Human output is a single search-style hit without a score:

```text
Source: manual.pdf
Page: 117
Heading: Chapter 4 > Detention Design

Detention shall be provided...
```

### `vera search FILE_OR_DIRECTORY QUERY`

Options:

- `--mode semantic|keyword|hybrid` defaults to `hybrid`.
- `--top-k N` defaults to `10` and must be non-negative.
- `--context-chunks N` defaults to `0` and must be non-negative.
- `--figures` adds figure metadata to JSON results.
- `--regions` adds page highlight regions to JSON results.
- `--recursive` discovers nested archives for an unindexed directory.
- `--exclude PATTERN` excludes a relative path or name pattern and is
  repeatable.
- `--include PATTERN` includes only matching relative paths and is
  repeatable. If any include is present, a file must match at least one
  include and no exclude. Directory search only; a single-file target
  exits 2 with `{"ok": false, "error": "--include applies to directory search only"}`.
- `--where KEY=VALUE` filters stored archive and chunk metadata before
  `top_k` and is repeatable. Distinct keys are AND. Comma-separated values
  are IN. Repeated flags for the same key union the IN set. Values coerce
  like `--pipeline-option`. A missing key fails the predicate. List-valued
  *stored* metadata is not an IN clause. Empty comma tokens are an error
  (exit 2). Do not post-filter the JSON `results` array. Desktop Search
  and Ask have no `--where` control.
- `--json` emits one JSON object.

Single-archive JSON:

```json
{
  "query": "stormwater detention requirements",
  "mode": "hybrid",
  "results": [
    {
      "chunk_id": "chunk_0042",
      "score": 0.91,
      "text": "Detention shall be provided...",
      "page_start": 117,
      "page_end": 117,
      "heading_path": "Chapter 4 > Detention Design",
      "source_filename": "manual.pdf",
      "document_id": "document_0001"
    }
  ]
}
```

There is no result `rank` field and no top-level `file` field for a
single-archive search. Rank is the position in the `results` array.

Directory/corpus JSON adds `file` to each result, an `index` object,
`skipped_files` diagnostics, and `skipped_semantic_model_groups` diagnostics:

```json
{
  "query": "stormwater detention requirements",
  "mode": "hybrid",
  "results": [
    {
      "chunk_id": "chunk_0042",
      "score": 0.91,
      "text": "Detention shall be provided...",
      "page_start": 117,
      "page_end": 117,
      "heading_path": "Chapter 4 > Detention Design",
      "source_filename": "manual.pdf",
      "document_id": "document_0001",
      "file": "C:/library/manual.vera"
    }
  ],
  "index": {
    "used": true,
    "exists": true,
    "fresh": true,
    "directory": "C:/library",
    "index": "C:/library/.vera-index",
    "reasons": []
  },
  "skipped_files": [
    {
      "file": "C:/library/bad.vera",
      "category": "invalid",
      "reason": "Missing required table: vera_metadata"
    }
  ],
  "skipped_semantic_model_groups": [
    {
      "model_name": "sentence-transformers/all-MiniLM-L6-v2",
      "dimension": 384,
      "error": "ImportError: No module named 'sentence_transformers'"
    }
  ]
}
```

The `index` object may contain additional status fields. When `used` is false,
search fell back to direct corpus search. Read `reasons` to explain why.
Malformed archives are skipped instead of aborting the library; read
`skipped_files` for absolute paths and validation reasons.
For indexed semantic and hybrid searches, read
`skipped_semantic_model_groups` for model groups omitted because their query
embedder was unavailable or had a dimension mismatch. Hybrid keyword matches
may still be returned when this array is non-empty.

With `--context-chunks N`, each result adds `before_chunks` and `after_chunks`.
Each context object contains:

```json
{
  "chunk_id": "chunk_0041",
  "text": "Previous text...",
  "page_start": 116,
  "page_end": 116,
  "heading_path": "Chapter 4 > Detention Design",
  "source_filename": "manual.pdf",
  "document_id": "document_0001"
}
```

With `--figures`, each result adds a `figures` array. Figure objects contain:

```json
{
  "block_id": "block_0037",
  "page_number": 117,
  "bbox": [72.0, 144.0, 540.0, 420.0],
  "page_width": 612.0,
  "page_height": 792.0,
  "asset_id": "asset_block_0037",
  "mime_type": "image/png",
  "filename": "figure-4-1.png",
  "caption": "Figure 4-1: Detention sizing"
}
```

The CLI does not include image bytes.

With `--regions`, each result adds a `regions` array:

```json
{
  "block_id": "block_0042",
  "page_number": 117,
  "bbox": [72.0, 430.0, 540.0, 510.0],
  "page_width": 612.0,
  "page_height": 792.0
}
```

Bounding boxes are `[x0, y0, x1, y1]` in page points with a top-left origin.

An empty successful search has `results: []` and exit code 0. Missing paths,
directories with no archives, and runtime failures generally produce an
unstructured exception on stderr and exit 1.

### `vera index build DIRECTORY`

Options:

- `--recursive` discovers nested archives.
- `--exclude PATTERN` is repeatable.
- `--include PATTERN` is repeatable and is stored in index discovery
  settings like excludes. `vera index update` keeps saved includes.
- `--json` emits one JSON object.

This command creates or replaces the hidden `.vera-index/` collection index.
Indexing writes a unique temporary sibling; publication takes
`.vera-index/build.lock`, then deletes every other generation directory.
An empty discovery set raises unstructured `No .vera files found in ...`
(exit 1, no JSON). Recursive discovery is off by default.

```json
{
  "ok": true,
  "operation": "build",
  "directory": "C:/library",
  "index": "C:/library/.vera-index",
  "recursive": true,
  "excludes": ["archive/**"],
  "includes": [],
  "discovered": 12,
  "indexed": 11,
  "chunks": 4200,
  "skipped": 1,
  "invalid": [{"file": "bad.vera", "reason": "validation failed"}],
  "incompatible": [],
  "added": 11,
  "changed": 0,
  "moved": 0,
  "removed": 0
}
```

`invalid` and `incompatible` entries contain `file` and `reason`.

### `vera index update DIRECTORY`

Options: `--json`.

Rebuilds an existing index using its saved recursive and exclusion settings.
Its JSON shape matches `index build`, with `"operation": "update"` and change
counts describing the rebuild. If no index exists, the command raises an
unstructured error and exits 1.

### `vera index status DIRECTORY`

Options: `--json`.

CLI status hashes indexed archives (`verify_hashes` defaults to true;
`verified_at` is set). Directory search and `VeraCorpus.open` use
size/mtime only (`verify_hashes=false`; `verified_at` is null). The desktop
index badge uses that fast check; **Inspect** on a library folder refreshes
with full hashes.

Missing index:

```json
{
  "directory": "C:/library",
  "index": "C:/library/.vera-index",
  "exists": false,
  "fresh": false,
  "reasons": ["index is missing"]
}
```

Existing index:

```json
{
  "directory": "C:/library",
  "index": "C:/library/.vera-index",
  "exists": true,
  "fresh": true,
  "reasons": [],
  "generation_id": "generation-abc123",
  "created_at": "2026-08-02T22:55:00+00:00",
  "checked_at": "2026-08-02T22:56:00+00:00",
  "verified_at": "2026-08-02T22:56:00+00:00",
  "index_size_bytes": 24117248,
  "database_size_bytes": 1048576,
  "vector_size_bytes": 23068672,
  "recursive": true,
  "excludes": [],
  "file_count": 12,
  "skipped": 0,
  "skipped_files": [],
  "discovered": 12,
  "indexed_chunks": 1500,
  "source_chunks": 1500,
  "model_groups": [
    {
      "model": "vera-hashing-384",
      "dimension": 384,
      "documents": 12,
      "chunks": 1500,
      "vector_file": "vectors-abc123-384.npy",
      "vector_size_bytes": 23068672
    }
  ]
}
```

Exit code is 0 only when `fresh` is true. A missing, stale, corrupt, or
unsupported index still prints this JSON report and exits 1.
`indexed_chunks` counts rows written into FTS and vector matrices;
`source_chunks` counts chunk rows from successfully indexed archives.
Current builds keep these equal. Existing indexes built before these metrics
were introduced report indexed chunks as their source-chunk count until the
next rebuild.

### `vera validate FILE`

Options: `--json`.

```json
{
  "file": "manual.vera",
  "path": "C:/docs/manual.vera",
  "ok": true,
  "issues": [],
  "warnings": [],
  "counts": {
    "chunks": 480,
    "embeddings": 480,
    "fts_rows": 480,
    "attachments": 8
  },
  "checks": {
    "sqlite_integrity": "ok",
    "required_tables_present": true,
    "original_document_present": true
  },
  "metadata": {}
}
```

The exact `checks` and `metadata` keys can grow. An invalid archive prints the
report and exits 1.

### `vera export FILE [OUTPUT]`

Options: `--json`.

If `OUTPUT` is omitted, the stored source filename is used. If it names a
directory, the source is written inside it.

Success:

```json
{
  "ok": true,
  "output": "C:/exports/manual.pdf",
  "filename": "manual.pdf",
  "mime_type": "application/pdf",
  "hash": "sha256:..."
}
```

If no original was stored, JSON mode prints:

```json
{
  "ok": false,
  "error": "Original source document is not stored in this archive"
}
```

and exits 1.

### `vera figures FILE`

`FILE` is a single `.vera` archive. The command does not search a directory.

Options:

- `--out-dir DIR` writes image files under that directory and adds `path` to
  each figure object. Omitted, the command lists metadata only.
- `--asset-id ID` limits output to one figure attachment id and is repeatable.
- `--page-start N` includes figures on or after this 1-based page.
- `--page-end N` includes figures on or before this 1-based page.
- `--json` emits one JSON object.

List-only success (`--out-dir` omitted). There is no `path` field:

```json
{
  "ok": true,
  "file": "manual.vera",
  "out_dir": null,
  "figures": [
    {
      "block_id": "block_000042",
      "page_number": 1,
      "bbox": [72, 120, 272, 270],
      "page_width": 612,
      "page_height": 792,
      "asset_id": "image_block_000042",
      "mime_type": "image/png",
      "filename": "image_000001.png",
      "caption": "Figure 3: Detention pond sizing diagram"
    }
  ]
}
```

With `--out-dir`, files are named `{asset_id}.{ext}` (`ext` from mime type or
stored filename) and each object gains `path`. JSON never includes image
bytes or `data`.

```json
{
  "ok": true,
  "file": "manual.vera",
  "out_dir": "figures",
  "figures": [
    {
      "block_id": "block_000042",
      "page_number": 1,
      "bbox": [72, 120, 272, 270],
      "page_width": 612,
      "page_height": 792,
      "asset_id": "image_block_000042",
      "mime_type": "image/png",
      "filename": "image_000001.png",
      "caption": "Figure 3: Detention pond sizing diagram",
      "path": "figures/image_block_000042.png"
    }
  ]
}
```

A missing or non-figure `--asset-id` prints:

```json
{
  "ok": false,
  "error": "Figure 'image_block_missing' was not found"
}
```

and exits 1. An empty list with no filter is success (exit 0). `--out-dir`
must be a directory; a file path exits 1 with a structured error. An unsafe
`asset_id` (absolute, `..`, or path separators) also exits 1.

Search `--figures` still returns metadata only. Use this command (or MCP
`vera_get_figure`) when you need the stored raster.

### `vera eval FILE QUERIES`

`FILE` is a single `.vera` archive. The command does not search a directory or
collection index.

Options:

- `--mode semantic|keyword|hybrid|all` defaults to `all`.
- `--top-k N` defaults to `5`.
- `--json` emits one JSON object.

`QUERIES` is a JSON list, or YAML when PyYAML is installed:

```json
[
  {
    "query": "restaurant parking",
    "expected_pages": [42, 43],
    "expected_terms": ["parking"],
    "note": "optional"
  }
]
```

Result:

```json
{
  "file": "manual.vera",
  "queries_file": "queries.json",
  "reports": [
    {
      "mode": "hybrid",
      "top_k": 5,
      "total": 1,
      "hits": 1,
      "hit_rate": 1.0,
      "mrr": 1.0,
      "queries": [
        {
          "query": "restaurant parking",
          "note": "optional",
          "hit": true,
          "rank": 1,
          "top_score": 0.91,
          "top_page": 42
        }
      ]
    }
  ]
}
```

This command exits 0 only when every case in every requested mode hits. A miss
still prints the report and exits 1.

### `vera mcp`

Runs the long-lived stdio MCP server. It does not accept `--json`; protocol
messages use stdout, so do not mix ordinary output into that stream.

MCP provides `vera_search`, `vera_corpus_search`, `vera_inspect`,
`vera_validate`, `vera_figures`, `vera_get_figure`, `vera_get_page`,
`vera_get_chunk`, and
`vera_get_chunk_regions`. `vera_search` and `vera_corpus_search` default
`top_k` to `10`, matching `vera search` and `VeraDocument.search`.
`vera_inspect` and `vera_validate` include both `file` (requested) and
`path` (opened). `vera_get_figure` returns native image content for one
`asset_id` plus citation metadata; a missing id returns `{"error": "..."}`.
`vera_get_chunk` matches `vera get FILE CHUNK_ID --json`, including `ok: true`
and locator fields; a missing chunk returns `{"ok": false, "error": "chunk not
found: ..."}` rather than raising. `vera_get_page` and `vera_get_chunk_regions`
have no direct standalone CLI equivalent. `vera figures` is the CLI equivalent of `vera_figures` listing.
See the repository's agent-skills guide for MCP setup.

### `vera ocr-languages list [LANGUAGE]`

Options: `--json`.

Reports Tesseract language codes usable by the `pymupdf` parser without
running a conversion. `LANGUAGE` optionally limits the report to specific
`+`-joined codes (e.g. `eng+fra`); omitted, it lists every bundled and
registry code.

```json
{
  "ok": true,
  "languages": [
    {"code": "eng", "name": "English", "bundled": true, "downloadable": true, "cached": true},
    {"code": "fra", "name": "French", "bundled": false, "downloadable": true, "cached": false, "size_bytes": 1130365},
    {"code": "zzz", "name": "zzz", "bundled": false, "downloadable": false, "cached": false}
  ]
}
```

`bundled` codes never touch the network or the cache directory. `cached`
means the code is already available in the local cache (or bundled).
`downloadable: false` means the code is not in VERA's curated registry;
`vera ocr-languages download` will fail for it, and it requires a manually
installed `.traineddata` file with `TESSDATA_PREFIX` set. Unrecognized codes
are still listed (with their raw code standing in for `name`) so agents can
render a consistent table instead of erroring.

### `vera ocr-languages download LANGUAGE`

Options: `--json`.

Fetches `+`-joined Tesseract language code(s) (e.g. `fra` or `fra+deu`) into
the local cache, verifying each download's SHA-256 against VERA's pinned
registry before it is written. Codes already valid in the cache are reused
without a network request — safe to call repeatedly. The cache directory
defaults to a per-user location and can be overridden with the
`VERA_TESSDATA_CACHE` environment variable (checked by both this command and
`--ocr-allow-download`).

```json
{
  "ok": true,
  "language": "fra",
  "downloaded": ["fra"],
  "cache_dir": "/home/user/.cache/vera/tessdata"
}
```

A code with no bundled or registry data exits 2 with:

```json
{
  "ok": false,
  "error": "OCR language 'zzz' has no bundled data and is not in VERA's download registry. Downloadable codes: afr, ara, ces, ... Install a Tesseract .traineddata file manually and set TESSDATA_PREFIX instead."
}
```

A network or checksum failure also exits 2 with a structured `error` and
never leaves a partially-written file in the cache.

## Exit and output rules

All JSON-capable commands print one JSON object to stdout on success. Check the
exit code before deciding how to interpret output:

- Exit 0: parse stdout as JSON when `--json` was supplied.
- Exit 1 with structured JSON: expected negative result from `validate`,
  `index status`, `eval`, `export` without an embedded source, `figures` when a
  requested `--asset-id` is missing or is not a figure, `get` when the chunk
  id is missing, or `convert`
  when extraction/validation fails or the input path is missing (`{ok: false,
  error}`).
- Exit 1 with stderr traceback: most path, dependency, or runtime failures.
- Exit 1 after batch report: one or more directory conversions failed or an
  existing output was malformed.
- Exit 2: argparse usage/type failure, an output path supplied for directory
  conversion, an unknown `parser`/`model`, or a failed `ocr-languages
  download` (unknown code, network error, or checksum mismatch — convert
  unknown-provider and `ocr-languages download` failures emit structured JSON
  under `--json`).

Do not assume stderr is JSON. Do not discard stdout solely because the exit code
is 1; first check whether the command is one of the documented structured
negative-result cases.

## Filesystem effects

- Read-only: `search`, `inspect`, `get`, `validate`, `eval`, `ocr-languages list`,
  and `figures` without `--out-dir`.
- Writes archives: `convert`; existing single outputs can be replaced.
  `convert --ocr-allow-download` (and `ocr-languages download`) can also
  write into the OCR language cache directory.
- Writes collection artifacts: `index build`, `index update`.
- Writes source files: `export`.
- Writes figure image files: `figures --out-dir`.
- Writes to the OCR language cache directory: `ocr-languages download`.
- Long-running process: `mcp`.
- Network access: `convert --ocr-allow-download` and `ocr-languages
  download` are the only commands that make outbound network requests
  (fetching curated Tesseract language data); every other command is fully
  offline.
