---
name: vera
description: "Search PDFs and local document libraries with vera-cli to retrieve citation-ready context for AI agents. VERA converts PDFs into portable .vera archives containing text chunks, embeddings, figures, and source metadata, providing local keyword, semantic, and hybrid retrieval without a separate vector database or retrieval service. Use when answering questions from local documents, searching one archive or a document library, finding figures or page regions, checking archive integrity, converting PDFs, indexing a VERA library, or operating vera-cli."
license: Apache-2.0
compatibility: Requires Python 3.10+, vera-cli on PATH or importable as vera_cli, and shell and local file access.
metadata:
  author: dkylewillis
  version: "0.1.1"
---

# VERA

VERA allows AI agents to search PDFs and local document libraries, retrieve
relevant passages, and produce answers grounded in the original source.

The VERA CLI converts PDFs into portable `.vera` archives containing document
chunks, embeddings, figures, and citation metadata. These archives support
local keyword, semantic, and hybrid retrieval without requiring a separate
vector database or retrieval service.

Use `vera-cli` to retrieve grounded evidence from `.vera` archives. Prefer JSON
output, evaluate the returned text rather than relying on scores alone, and
cite the source page and heading for every document-backed claim.

## Before running commands

1. Check whether `vera --help` succeeds.
2. If the console script is unavailable, try `python -m vera_cli --help`.
3. If neither works, tell the user that `vera-cli` must be installed. Do not
   install packages or modify the environment unless the user has authorized
   those changes.
4. Quote paths and queries according to the active shell.

Use `vera` in the examples below. Substitute `python -m vera_cli` when
necessary.

Read [references/cli-reference.md](references/cli-reference.md) before using
commands beyond ordinary search or when exact JSON, field, and exit-code
behavior matters. Read
[references/retrieval-workflows.md](references/retrieval-workflows.md) for
multi-step research, corpus searches, identifier lookup, figure retrieval, and
insufficient-evidence workflows.

## Default search workflow

1. Identify the `.vera` archive or directory and the question.
2. Begin with a high-recall hybrid search:

   ```bash
   vera search "manual.vera" "stormwater detention requirements" --mode hybrid --top-k 5 --json
   ```

3. Check the process exit code. On success, parse stdout as one JSON object.
4. Review each result's `text`, `page_start`, `page_end`, `heading_path`, and
   `source_filename`. For directory searches, also retain `file`.
5. Determine whether the evidence directly answers the question. Refine the
   query, change modes, or increase coverage when it is incomplete. Do not
   treat rank or score as proof.
6. Answer only from retrieved evidence and cite every substantive claim.

Search a directory as one corpus by passing the directory instead of a file:

```bash
vera search "./library" "stormwater detention requirements" --mode hybrid --top-k 5 --json
```

Use `--recursive` for nested directories that are not covered by an index.
When searching a directory, inspect `index.used` and `index.reasons` rather
than assuming an index was used; review `skipped_files` for malformed archives
excluded from the search; and for indexed semantic or hybrid searches review
`skipped_semantic_model_groups` (missing or incompatible query embedders may
leave semantic coverage incomplete even when keyword results are returned).

Collection indexes persist under `.vera-index/` across process restarts.
Status checks and library searches do not rebuild them; use `index update`
after the source library changes.

## Choose retrieval options

- Start with `--mode hybrid`.
- Use `--mode keyword` for exact phrases, identifiers, section numbers,
  ordinance or code references, table labels, and document-specific
  terminology. Confirm the relevant token appears in the returned text;
  punctuation and short hyphenated identifiers may be tokenized broadly.
- Use `--mode semantic` for paraphrases, concepts with different wording,
  purpose or intent, and queries where exact terminology is unknown.
- Add `--context-chunks 1` when a hit depends on nearby definitions,
  exceptions, qualifications, or preceding steps.
- Add `--figures` for figures, tables, charts, diagrams, maps, and captions.
- Add `--regions` only when page bounding boxes or visual-grounding
  coordinates are required.
- Increase `--top-k` to 10 for broader coverage. Split compound questions into
  separate searches when each part needs different evidence.

## Citations and evidence

Format citations as:

- `(source.pdf, p. 42, Chapter 4 > Detention Design)`
- `(source.pdf, pp. 42-43)` when a result spans pages

For directory or corpus searches, preserve both the source archive and the
original source filename when available. When comparing documents, keep each
source's evidence and conclusions clearly separated.

Treat evidence as strong when the retrieved text directly states the relevant
definition, requirement, threshold, procedure, exception, limitation, or
conclusion. Search again when a result only shares generic vocabulary, lacks
the exact identifier, does not directly support the claim, conflicts with
another source, or appears incomplete without surrounding context.

Do not cite a page merely because it ranked highly. Read the returned text and
verify that it supports the claim.

For figures, cite the caption and page. `--figures` returns metadata and
captions, not image pixels. Do not claim to have visually inspected an image
unless a separate vision-capable tool actually viewed it. Use `--regions` when
page coordinates are needed to highlight retrieved evidence.

## Inspect and validate

Use inspection when archive identity, source information, embedding
configuration, or metadata matters:

```bash
vera inspect "manual.vera" --json
```

Inspection may report `default_embedding_normalization` as `l2`, `none`, or
`unknown`. Older archives without the field are reported as `unknown`.

Use validation when the user asks about archive integrity or a search failure
suggests that an archive may be malformed:

```bash
vera validate "manual.vera" --json
```

An invalid archive may return exit code 1 while still printing a structured
JSON validation report. Read the report before concluding that no useful
diagnostic is available.

## Commands that write files

`search`, `inspect`, `validate`, and `eval` are read-only. The following
commands create, replace, or modify local files and require normal user
authorization:

- `convert` creates a validated `.vera` archive and publishes it atomically.
  Image-based or low-text pages use selective local OCR by default. Use
  `--ocr off` only when the user explicitly requests it, or `--ocr force` when
  automatic detection misses a scan. English OCR is bundled; other languages
  require installed Tesseract language data.
- `convert --overwrite` replaces existing outputs.
- `index build` and `index update` write `.vera-index/`.
- `export` writes the embedded source document.

Never infer permission to convert, overwrite, index, update, or export from a
request that only asks to search, inspect, summarize, or explain a document.

## Failure handling

- Always inspect the exit code before trusting output.
- Do not assume every nonzero exit lacks JSON. `validate`, `index status`,
  `eval`, and a failed `export` can print useful JSON while returning 1.
- Most missing-path and runtime failures are unstructured tracebacks on
  stderr. Do not parse stderr as JSON.
- Directory conversion validates existing outputs before skipping them and
  exits 1 when `malformed_existing` is nonempty.
- When a command fails, read stdout and stderr separately, check for
  documented structured JSON, identify the failed path or operation, and
  report the failure clearly. Do not invent results or silently ignore skipped
  archives.

## Insufficient evidence

When no direct answer is found, report the queries and modes used, describe
the closest relevant evidence, explain what is still missing, and suggest a
narrower query, another mode, or additional documents when appropriate. Do not
turn weakly related text into a definitive answer.

## Verification

Before responding, verify that:

- the command completed and its output was interpreted using its documented
  exit behavior;
- every document-backed claim has a source, page or page range, and heading
  when available;
- exact identifiers appear in the supporting evidence;
- rank and score were not treated as proof;
- figure claims do not exceed the returned caption or metadata;
- archive or model-group omissions are disclosed when they affect coverage;
- uncertainty and missing evidence are stated explicitly;
- no write operation was performed without authorization.
