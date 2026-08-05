# CLI reference

The `vera` console script and `python -m vera_cli` expose the same command
parser.

```text
vera convert
vera inspect
vera search
vera index build
vera index update
vera index status
vera validate
vera export
vera eval
vera mcp
```

Run `vera COMMAND --help` for parser-generated usage. This page is the
human-oriented overview. The portable skill's
[exhaustive CLI contract](https://github.com/dkylewillis/vera/blob/main/skills/vera/references/cli-reference.md) documents
complete JSON object shapes, stdout/stderr behavior, exit codes, and filesystem
effects without duplicating that contract here.

## `vera convert INPUT [OUTPUT]`

Convert one PDF or a directory of PDFs.

Options:

- `--model MODEL` (`hashing`; accepts `provider:model-id` specs such as
  `sentence-transformers:all-MiniLM-L6-v2`; unknown providers exit with an
  error)
- `--parser PARSER` (`pymupdf`; accepts `provider[:variant]` specs such as
  `docling` / `docling:hybrid` when `vera-ingest-docling` is installed; unknown
  providers exit with an error)
- `--chunk-size N` (`500`)
- `--overlap N` (`75`)
- `--store-original VALUE` (`true`)
- `--ocr auto|off|force` (`auto`)
- `--ocr-language CODE` (`eng`)
- `--ocr-dpi N` (`300`, must be positive)
- `--recursive`
- `--overwrite`
- `--json`

Conversion selectively OCRs image-based low-text pages through PyMuPDF and
Tesseract, publishes a validated temporary archive atomically, and fails when
no searchable chunks are extracted. English language data is bundled for
offline, zero-setup OCR; other selected languages require external Tesseract
language data. Directory conversion writes archives beside PDFs, validates
existing outputs before skipping them, reports malformed outputs separately,
and does not accept `OUTPUT`.

## `vera inspect FILE`

Print archive metadata and summary counts, including archive size, creation
time, embedding dimensions and normalization policy, parser/chunking settings,
OCR diagnostics, and attachment count when recorded. Normalization is `l2`,
`none`, or `unknown`.

Options: `--json`.

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

Writes `.vera-index/` under the library root.

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

Options: `--json`.

Exits 1 when validation finds an issue while still emitting a report.

## `vera export FILE [OUTPUT]`

Write the embedded source document to its stored filename, a chosen path, or an
existing directory.

Options: `--json`.

## `vera eval FILE QUERIES`

Evaluate retrieval against expected pages or terms.

Options:

- `--mode semantic|keyword|hybrid|all` (`all`)
- `--top-k N` (`5`)
- `--json`

Exits 1 if any expected answer is missed while still emitting a report.

## `vera mcp`

Run the long-lived stdio MCP server. This command does not accept `--json`.
Install the `mcp` optional dependency first.

## JSON and exit codes

One-shot commands support `--json` and print one JSON object on success.

Do not assume nonzero output is unstructured:

- `validate` returns a report when the archive is invalid;
- `index status` returns a report when the index is stale or missing;
- `eval` returns a report when a query misses;
- `export` returns an error object when no source is stored.

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
