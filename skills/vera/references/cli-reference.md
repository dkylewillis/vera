# VERA CLI reference for agents

This reference describes the current `vera-cli` v0.1 command contract. The
console entry point is `vera`; `python -m vera_cli` invokes the same parser.

## Runtime and installation

- Python: 3.10 or newer.
- Published CLI: `pip install vera-cli`.
- Neural embedding models require the `ml` extra from `vera-doc`.
- `vera mcp` requires `pip install vera-cli "vera-doc[mcp]"`.
- A repository checkout can use:
  `uv sync --extra dev --extra ml --extra app --extra mcp`.

Check `vera --help` first. If it is not on `PATH`, try
`python -m vera_cli --help`.

## Command inventory

### `vera convert INPUT [OUTPUT]`

Convert one PDF or a directory of PDFs.

Options:

- `--model MODEL` defaults to `hashing`.
- `--parser PARSER` defaults to `pymupdf`.
- `--chunk-size N` defaults to `500`.
- `--overlap N` defaults to `75`.
- `--store-original VALUE` defaults to `true`. Values `1`, `true`, `yes`, `y`,
  and `on` are true, case-insensitively; other values are false.
- `--recursive` recursively discovers PDFs in directory mode.
- `--overwrite` replaces existing outputs in directory mode.
- `--json` emits one JSON object.

For a single PDF, omitted `OUTPUT` defaults to the input basename with a
`.vera` suffix. The single-file conversion path replaces an existing output.
For a directory, outputs are written beside their PDFs. Supplying `OUTPUT` with
a directory is an error.

Single-file JSON:

```json
{
  "ok": true,
  "output": "C:/docs/manual.vera"
}
```

Directory JSON:

```json
{
  "ok": true,
  "directory": "C:/docs",
  "recursive": true,
  "overwrite": false,
  "discovered": 3,
  "converted": 2,
  "skipped": 1,
  "failed": 0,
  "outputs": ["C:/docs/a.vera", "C:/docs/nested/b.vera"],
  "skipped_existing": ["C:/docs/c.vera"],
  "errors": []
}
```

Each error entry has `input` and `error`. A partial batch failure prints the
report and exits 1. Supplying a directory and an output path prints an error to
stderr and exits 2.

### `vera inspect FILE`

Options: `--json`.

JSON combines the archive metadata with summary counts. Metadata is extensible,
so agents must tolerate additional keys.

```json
{
  "file": "manual.vera",
  "format_name": "VERA",
  "format_version": "0.1",
  "created_at": "2026-01-01T00:00:00+00:00",
  "source_file_name": "manual.pdf",
  "default_embedding_model": "hashing",
  "default_embedding_dimension": "384",
  "parser_name": "pymupdf",
  "source": "manual.pdf",
  "pages": 120,
  "chunks": 480,
  "embeddings": 480
}
```

Values read from `vera_metadata`, including numeric-looking values, may be
strings. `pages`, `chunks`, and `embeddings` are integers.

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

Directory/corpus JSON adds `file` to each result and an `index` object:

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
  }
}
```

The `index` object may contain additional status fields. When `used` is false,
search fell back to direct corpus search. Read `reasons` to explain why.

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
- `--json` emits one JSON object.

This command creates or replaces the hidden `.vera-index/` collection index.

```json
{
  "ok": true,
  "operation": "build",
  "directory": "C:/library",
  "index": "C:/library/.vera-index",
  "recursive": true,
  "excludes": ["archive/**"],
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
  "recursive": true,
  "excludes": [],
  "file_count": 12,
  "skipped": 0,
  "discovered": 12
}
```

Exit code is 0 only when `fresh` is true. A missing, stale, corrupt, or
unsupported index still prints this JSON report and exits 1.

### `vera validate FILE`

Options: `--json`.

```json
{
  "file": "manual.vera",
  "ok": true,
  "issues": [],
  "warnings": [],
  "counts": {
    "documents": 1,
    "pages": 120,
    "chunks": 480,
    "embeddings": 480,
    "fts_rows": 480,
    "assets": 8
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

### `vera eval FILE QUERIES`

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
`vera_validate`, `vera_figures`, `vera_get_page`, and
`vera_get_chunk_regions`. The final three have no direct standalone CLI
equivalent. See the repository's agent-skills guide for MCP setup.

## Exit and output rules

All JSON-capable commands print one JSON object to stdout on success. Check the
exit code before deciding how to interpret output:

- Exit 0: parse stdout as JSON when `--json` was supplied.
- Exit 1 with structured JSON: expected negative result from `validate`,
  `index status`, `eval`, or `export` without an embedded source.
- Exit 1 with stderr traceback: most path, dependency, or runtime failures.
- Exit 1 after batch report: one or more directory conversions failed.
- Exit 2: argparse usage/type failure or an output path supplied for directory
  conversion.

Do not assume stderr is JSON. Do not discard stdout solely because the exit code
is 1; first check whether the command is one of the documented structured
negative-result cases.

## Filesystem effects

- Read-only: `search`, `inspect`, `validate`, `eval`.
- Writes archives: `convert`; existing single outputs can be replaced.
- Writes collection artifacts: `index build`, `index update`.
- Writes source files: `export`.
- Long-running process: `mcp`.
