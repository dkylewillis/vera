---
name: vera
description: Searches, inspects, validates, converts, indexes, and exports VERA (.vera) document archives with citation-ready results. Use when answering questions from local documents, searching one archive or a document library, finding figures or page regions, checking archive integrity, converting PDFs, or operating vera-cli.
license: Apache-2.0
compatibility: Requires Python 3.10+, vera-cli on PATH or importable as vera_cli, and shell and local file access.
metadata:
  author: vera-retrieval
  version: "1.0.0"
---

# VERA

Use `vera-cli` to retrieve grounded evidence from `.vera` archives. Prefer the
CLI's JSON output, read the returned text, and cite the source page and heading
for every document-backed claim.

## Before running commands

1. Check whether `vera --help` succeeds.
2. If the console script is unavailable, try `python -m vera_cli --help`.
3. If neither works, tell the user that `vera-cli` must be installed. Do not
   install packages unless the user has authorized environment changes.
4. Quote paths and queries according to the active shell.

Use `vera` in examples below. Substitute `python -m vera_cli` when necessary.

Read [references/cli-reference.md](references/cli-reference.md) before using
commands beyond ordinary search or when exact JSON and exit-code behavior
matters. Read
[references/retrieval-workflows.md](references/retrieval-workflows.md) for
multi-step research, corpus, identifier, figure, and insufficient-evidence
workflows.

## Default search workflow

1. Identify the `.vera` file or directory and the question.
2. Run a high-recall first search:

   ```bash
   vera search "manual.vera" "stormwater detention requirements" --mode hybrid --top-k 5 --json
   ```

3. Check the process exit code. On success, parse stdout as one JSON object.
4. Read each result's `text`, `page_start`, `page_end`, `heading_path`, and
   `source_filename`. For directory searches, also retain each result's `file`.
5. If the evidence does not directly answer the question, refine the query or
   switch modes. Do not treat rank or score as proof.
6. Answer only from retrieved evidence and cite each substantive claim.

Search a directory as one corpus by passing the directory instead of a file:

```bash
vera search "./library" "stormwater detention requirements" --top-k 5 --json
```

Use `--recursive` for a nested, unindexed directory. A fresh local index is used
automatically when one exists; inspect the top-level `index.used` and
`index.reasons` fields instead of assuming the index was active.

## Choose retrieval options

- Start with `--mode hybrid`.
- Use `--mode keyword` for exact phrases, identifiers, section numbers, table
  labels, and codes. Confirm that the exact token appears in returned text;
  punctuation and short hyphenated identifiers may be tokenized broadly.
- Use `--mode semantic` for paraphrases, intent, purpose, and wording mismatch.
- Add `--context-chunks 1` when a hit depends on nearby definitions, exceptions,
  or preceding steps.
- Add `--figures` for figures, tables, charts, diagrams, maps, and captions.
- Add `--regions` only when page bounding boxes are needed for visual grounding.
- Increase `--top-k` to 10 for broad coverage; split compound questions into
  separate searches.

## Citations and evidence

Format citations as:

- `(source.pdf, p. 42, Chapter 4 > Detention Design)`
- `(source.pdf, pp. 42-43)` when a result spans pages

For corpus results, preserve the source archive and source filename. When
comparing archives, keep evidence and conclusions separated by source.

Treat evidence as strong when the text directly states the relevant definition,
requirement, threshold, procedure, or exception under a relevant heading.
Search again when a result only shares generic vocabulary, lacks the exact
identifier, or conflicts with another result.

For figures, cite the caption and page. `--figures` returns metadata and
captions, not image pixels. Do not claim to have visually inspected an image
unless a separate vision-capable tool actually read it.

## Inspect and validate

Use inspection when source identity or archive metadata matters:

```bash
vera inspect "manual.vera" --json
```

Use validation when the user asks about archive integrity or a search failure
suggests corruption:

```bash
vera validate "manual.vera" --json
```

`validate --json` intentionally returns exit code 1 for an invalid archive
while still printing a structured report. Read the report before concluding
that no usable diagnostic exists.

## Commands that write files

`search`, `inspect`, `validate`, and `eval` are read-only. The following
commands write or replace local files and require normal user authorization:

- `convert` creates a `.vera` archive; single-file output may be replaced.
- `convert --overwrite` replaces existing batch outputs.
- `index build` and `index update` write `.vera-index/`.
- `export` writes the embedded source document.

Never infer permission to convert, overwrite, index, update, or export from a
request that only asks to search or explain a document.

## Failure handling

- Always inspect the exit code before trusting output.
- Do not assume all nonzero exits lack JSON. `validate`, `index status`, `eval`,
  and a failed `export` can print useful JSON while returning 1.
- Most missing-path and runtime failures are unstructured tracebacks on stderr.
  Do not parse stderr as JSON.
- `vera mcp` is a long-running stdio server and does not accept `--json`.
- If no direct answer is found, report the queries and modes tried and describe
  the closest evidence without inventing an answer.

## Verification

Before responding, verify that:

- the command completed and its output was interpreted using its documented
  exit behavior;
- every document-backed claim has a source, page or page range, and heading
  when available;
- exact identifiers appear in the evidence;
- figure claims do not exceed the returned metadata;
- uncertainty and missing evidence are explicit.
