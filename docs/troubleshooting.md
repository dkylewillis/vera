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
[Search documents](searching.md).

## Exact identifiers produce broad matches

Keyword fallback can strip punctuation and create prefix terms. For a short
code such as `EL-A`:

```bash
vera search "manual.vera" "EL-A zoning district" --mode keyword --top-k 10 --json
```

Confirm that the literal identifier appears in result text before reporting a
match.

## A neural-model archive fails to search

Archives record the embedding model used during conversion. Install the
optional machine-learning dependency:

```bash
python -m pip install "vera-doc[ml]"
```

The required Sentence Transformers model may also need to be available in the
runtime environment. The default hashing model does not require this extra.

An unrecognized model name falls back to hashing but is retained in
archive metadata. If a custom name was used accidentally, reconvert with
`--model hashing` or a supported Sentence Transformers name.

## Validation fails because the original is missing

An archive created with:

```bash
vera convert "input.pdf" --store-original false
```

is searchable but does not contain the source PDF. The current validator
reports this as an issue, and export is unavailable. Reconvert with the default
`--store-original true` if source preservation is required.

## Export reports that no source is stored

The archive was created without the original document or is damaged. Export
cannot reconstruct the PDF from parsed text. Locate the source PDF and
reconvert it. In the desktop app, right-click the `.vera` file and choose
**Reconvert…** when the original PDF is beside the archive or stored inside it.

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
stale.

## Index update says no index exists

Build it first:

```bash
vera index build "./library" --recursive --json
```

`index update` only works when saved index configuration already exists.

## Conversion skips files

Directory conversion validates existing same-named `.vera` files before
skipping them. Review `skipped_existing` for valid skips and
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

If an English error says the bundled model is missing, reinstall VERA. Languages
other than `eng` are not bundled: install the requested `.traineddata` file and
set `TESSDATA_PREFIX` to its containing directory. `--ocr-language` accepts
Tesseract language codes such as `deu` or `eng+spa`.

An OCR pass can still produce no searchable text when the scan is blank,
low-resolution, handwritten, or mostly diagrams. VERA's selective OCR targets
prose and does not reconstruct scanned tables, forms, or complex multi-column
layouts. Preprocess those files with a layout-aware OCR tool before converting.
A failed conversion does not replace an existing destination and removes its
temporary output.

## Conversion fails for a parser name

`--parser` must name an installed ingest pipeline (`provider[:variant]`). The
default provider is `pymupdf` (from `vera-ingest-pymupdf`):

```bash
vera convert "input.pdf" --parser pymupdf
```

For Docling, install the optional plugin first:

```bash
uv sync --extra docling
vera convert "input.pdf" --parser docling
```

Unknown names fail before parsing and never fall back to another pipeline.

If Hugging Face Hub downloads warn about unauthenticated requests or hit rate
limits, set `HF_TOKEN` (see `.env.example`) or save a token under **File >
LLM Providers → Hugging Face** in the desktop app.

## Figures are missing or have no caption

- Search with `--figures --json`; figure metadata is not shown in ordinary text
  output.
- Search the caption wording and the subject.
- Some PDF tables are text blocks rather than image assets.
- Captions are linked by page layout and proximity and may be `null`.

## Highlight boxes cover extra text

Regions are block-granular, not word-precise. A chunk that starts or ends
inside a layout block maps to the whole block. This is expected behavior.

## JSON parsing fails on a nonzero exit

Check the command:

- `validate`, `index status`, `eval`, and failed `export` can return structured
  JSON with exit status 1;
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
