---
name: vera
description: Searches, inspects, validates, converts, indexes, and exports VERA (.vera) document archives with citation-ready results. Use when answering questions from local documents, searching one archive or a document library, finding figures or page regions, checking archive integrity, converting PDFs or Markdown, or operating vera-cli.
license: Apache-2.0
compatibility: Requires Python 3.10+, vera-cli on PATH or importable as vera_cli, and shell and local file access.
metadata:
  author: vera-retrieval
  version: "1.0.0"
---

# VERA

Frontmatter `metadata.version` is this skill's schema version, not the VERA
product (0.3.x) or archive format (0.2).

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
5. When you need the stored chunk body or to verify a quote, reload that
   `chunk_id` with `vera get FILE CHUNK_ID --json` instead of searching again.
6. If the evidence does not directly answer the question, refine the query or
   switch modes. Do not treat rank or score as proof.
7. Answer only from retrieved evidence and cite each substantive claim.

Search a directory as one corpus by passing the directory instead of a file:

```bash
vera search "./library" "stormwater detention requirements" --top-k 5 --json
```

Filter a corpus with stored metadata or path includes instead of post-filtering
JSON:

```bash
vera search "./archives" "adding capacity" --where company=GRID --json
vera search "./research" "adding capacity" --recursive --include "companies/GRID/archives/**" --json
```

Use `--recursive` for a nested, unindexed directory. A fresh local index is used
automatically when one exists; inspect the top-level `index.used` and
`index.reasons` fields instead of assuming the index was active. Also inspect
`skipped_files`: malformed archives are excluded from results and reported
with their paths and validation reasons. For indexed semantic or hybrid
searches, also inspect `skipped_semantic_model_groups`: unavailable or
dimension-incompatible query embedders are omitted, so semantic coverage is
incomplete even though keyword matches may still be returned.
Collection indexes persist under `.vera-index/` across process restarts.
Status checks and library opens do not rebuild them; use `index update`
explicitly after the source library changes. A successful rebuild deletes
every other generation directory; do not treat leftover generations as
rollback history. `vera eval` opens one `.vera` archive, not a directory.

## Choose retrieval options

- Start with `--mode hybrid`.
- Use `--mode keyword` for exact phrases, identifiers, section numbers, table
  labels, and codes. Confirm that the exact token appears in returned text;
  punctuation and short hyphenated identifiers may be tokenized broadly.
- Use `--mode semantic` for paraphrases, intent, purpose, and wording mismatch.
- Add `--context-chunks 1` when a hit depends on nearby definitions, exceptions,
  or preceding steps.
- Add `--figures` for charts, diagrams, maps, and captions. That flag returns
  metadata (`asset_id`, caption, page), not pixels. Fetch a stored raster with
  `vera figures FILE --out-dir DIR --json` (attach the `path`) or MCP
  `vera_get_figure`. Tables are usually markdown in chunk text, not figures.
  A missing `asset_id` means no stored raster (vector drawings, decorative
  marks); do not crop the PDF by hand.
- Add `--regions` only when page bounding boxes are needed for visual grounding.
- Increase `--top-k` to 10 for broad coverage; split compound questions into
  separate searches.
- Scope a library with `--where KEY=VALUE` (stored metadata, before `top_k`)
  or `--include PATTERN` (path discovery). Do not drop hits from JSON after
  search. Stamp keys at convert time with `--metadata KEY=VALUE`.

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
captions, not image pixels. To inspect a stored image, write it with
`vera figures FILE --out-dir DIR --json` and attach the file, or call MCP
`vera_get_figure`. Do not claim to have visually inspected an image unless
those bytes were actually read.

## Inspect and validate

Use inspection when source identity or archive metadata matters:

```bash
vera inspect "manual.vera" --json
```

Inspection includes `default_embedding_normalization`: `l2`, `none`, or
`unknown`. Older archives without the field are reported as `unknown`.
Package release 0.3.x versions the CLI and APIs; `format_version` remains
`0.2` and existing archives stay compatible.

Use validation when the user asks about archive integrity or a search failure
suggests corruption:

```bash
vera validate "manual.vera" --json
```

`validate --json` intentionally returns exit code 1 for an invalid archive
while still printing a structured report. Read the report before concluding
that no usable diagnostic exists.

## Commands that write files

`search`, `inspect`, `get`, `validate`, and `eval` are read-only. The following
commands write or replace local files and require normal user authorization:

- `convert` creates a validated `.vera` archive and publishes it atomically;
  omit `--parser` to choose an installed ingest pipeline from the file
  extension (`pdf` → `pymupdf` from `vera-ingest-pymupdf`; `md`/`markdown` →
  bundled `markdown`; `docx`/`pptx`/`xlsx`/`html`/`htm` → `docling` when
  `vera-cli[docling]` or `vera-ingest-docling` is installed). An explicit
  `--parser` that does not advertise the file's extension fails; there is no
  silent fallback.
  Image-based low-text PDF pages use selective local OCR by default. Use
  `--ocr off` only when explicitly requested, or `--ocr force` when automatic
  detection misses a scan. Prefer `--pipeline-option KEY=VALUE` for
  provider-owned settings; `--chunk-size`, `--overlap`, `--ocr`,
  `--ocr-language`, and `--ocr-dpi` remain compatibility aliases (Docling does
  not receive overlap/DPI or the Tesseract `--ocr-language` alias). English OCR
  is bundled in `vera-ingest-pymupdf`;
  other languages use `vera ocr-languages download`, `--ocr-allow-download`,
  or a manual `TESSDATA_PREFIX` install.
  Extra ingest plugins are pip packages in the same environment
  (`python -m pip install` or `python -m pip install -e <clone>`). MiniLM
  convert/search needs `vera-doc[ml]` (Sentence Transformers), or
  `vera-doc[onnx]` (ONNX Runtime) plus a VERA-exported snapshot. MiniLM uses
  ONNX Runtime when a snapshot is present and Sentence Transformers otherwise.
  Use `vera-doc[ml]` for all other Sentence Transformers models. The
  0.3.x packaged desktop app converts PDFs with PyMuPDF and Markdown with the
  bundled `markdown` pipeline; Docling is the
  `vera-cli[docling]` extra, not Advanced layout in Convert. OpenAI embeddings
  ship with `vera-cli` as `vera-embed-openai`; set `OPENAI_API_KEY`. Hashing
  remains the default. Archives converted with OpenAI are not portable for
  semantic search.
- `convert --overwrite` replaces existing batch outputs.
- `index build` and `index update` write `.vera-index/` and delete previous
  generation directories after a successful publish.
- `export` writes the embedded source document.

Never infer permission to convert, overwrite, index, update, or export from a
request that only asks to search or explain a document.

## Failure handling

- Always inspect the exit code before trusting output.
- Do not assume all nonzero exits lack JSON. `validate`, `index status`, `eval`,
  a failed `export`, a failed `figures`, a failed `get`, and a failed `convert` can print useful JSON while returning 1.
  `convert --json` also prints `{"ok": false, "error": "..."}` and exits 2 for an
  unknown `--parser` / `--model`.
- Most other missing-path and runtime failures are unstructured tracebacks on
  stderr. Do not parse stderr as JSON.
- Directory conversion skips an existing `.vera` only when it validates and
  its stored `source_file_hash` matches the current PDF, and exits 1 when
  `malformed_existing` is nonempty.
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
