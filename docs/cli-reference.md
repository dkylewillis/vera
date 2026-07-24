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
[exhaustive CLI contract](../skills/vera/references/cli-reference.md) documents
complete JSON object shapes, stdout/stderr behavior, exit codes, and filesystem
effects without duplicating that contract here.

## `vera convert INPUT [OUTPUT]`

Convert one PDF or a directory of PDFs.

Options:

- `--model MODEL` (`hashing`)
- `--parser PARSER` (`pymupdf`)
- `--chunk-size N` (`500`)
- `--overlap N` (`75`)
- `--store-original VALUE` (`true`)
- `--recursive`
- `--overwrite`
- `--json`

Directory conversion writes archives beside PDFs, skips existing outputs by
default, and does not accept `OUTPUT`.

## `vera inspect FILE`

Print archive metadata and summary counts.

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

Report whether an index exists and is fresh.

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
