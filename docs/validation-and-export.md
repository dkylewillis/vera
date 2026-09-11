# Inspect, validate, and export archives

VERA provides read-only inspection and validation commands plus an export
command for restoring the embedded source document.

## Inspect metadata

```bash
vera inspect "manual.vera"
```

Text mode prints a short identity card: format, source filename, page and
chunk counts, embedding model, dimensions, normalization, parser, and
creation time. Normalization is `l2`, `none`, or `unknown`; older archives
without the field report `unknown`. Pipeline diagnostics are **not** printed
in text mode.

For structured output, including diagnostics and caller `--metadata` tags:

```bash
vera inspect "manual.vera" --json
```

JSON spreads archive metadata at the top level and again under `metadata`.
`file` is the requested path; `path` is the opened archive. Metadata values
stored by the format may be strings even when they look numeric. Summary
counts such as `pages`, `chunks`, and `attachments` are integers.

### Pipeline diagnostics (`ocr`)

Convert always writes archive metadata `ocr` from the pipeline's
`diagnostics` dict (the key is historical; Docling recovery and Markdown
ingest use it too). An empty object means the pipeline recorded nothing —
Markdown's bundled pipeline leaves `ocr: {}`. Older archives may omit the
key.

| Pipeline | Always present | Conditional / notes |
| --- | --- | --- |
| PyMuPDF | `ocr_engine` (`tesseract`), `ocr_mode`, `ocr_language`, `ocr_dpi`, `ocr_pages` | `ocr_pages` is the 1-based list of pages that actually ran Tesseract. Empty means auto mode found no sparse image pages. |
| Docling | `engine` (`docling`), `variant`, `source_format`, `ocr_mode`, `ocr_language`, `ocr_languages`, `images_scale`, `torch_compile`, `layout_engine`, `tableformer_mode`, `overlap_ignored`, `artifacts_path_env`, `recovered_pages` | `pdf_backend` only for PDFs. `recovered_pages_backend` maps page number strings to the backend that recovered that page. `whole_document_fallback_backend` / `whole_document_fallback_strategy` (`document` or `batched`) appear after a whole-document `pypdfium2` fallback. Office/HTML omit `pdf_backend` and stay at `recovered_pages: []`. |
| Markdown | _(none — `ocr` is `{}`)_ | No OCR or page-recovery fields. |

Desktop **Document Info** summarizes `ocr` with PyMuPDF-shaped keys
(`ocr_engine`, `ocr_mode`, `ocr_language`, `ocr_dpi`, `ocr_pages`). Docling
stores `engine` rather than `ocr_engine` and records recovery in
`recovered_pages`, so the Info line can look like
`Auto · en · 0 pages OCR’d` even after a successful recovery. An empty
Markdown `ocr` object is truthy in the UI and shows
`Unknown mode · 0 pages OCR’d` instead of "Not recorded". Use
`vera inspect --json` (or the sidecar inspect payload) when the summary
looks wrong.

See [Docling reliability](packages/vera-ingest-docling.md#reliability-on-largecomplex-pdfs)
for the recovery sequence those fields describe.

## Validate integrity

```bash
vera validate "manual.vera"
```

Validation checks:

- SQLite integrity;
- required tables and metadata (`vera_metadata`, `chunks`, `embeddings`,
  `attachments`, `chunk_attachments`, `chunks_fts`);
- matching chunk, embedding, and FTS row counts;
- embedding blob dimensions and `float32_le` vector format;
- finite vectors and compliance with a declared L2 normalization policy;
- JSON object shape for chunk, attachment, and archive metadata;
- attachment SHA-256 checksums;
- presence of the original source document (warning when it is omitted).

JSON mode returns the full report:

```bash
vera validate "manual.vera" --json
```

The report includes `ok`, `issues`, `warnings`, `counts`, `checks`, and
`metadata`. Exit status is 0 when `ok` is true and 1 when validation finds an
issue. An invalid archive still emits the JSON report, so callers should retain
stdout when handling exit status 1.

An archive created with `--store-original false` is searchable. Validation
reports the missing original source as a warning rather than an issue.

## Export the original source

Export to the stored filename in the current directory:

```bash
vera export "manual.vera"
```

Choose a path:

```bash
vera export "manual.vera" "./exports/manual.pdf"
```

If the output names an existing directory, VERA writes the stored filename
inside that directory:

```bash
vera export "manual.vera" "./exports"
```

JSON mode reports the output path, stored filename, MIME type, and source hash:

```bash
vera export "manual.vera" "./exports" --json
```

If the archive does not contain the original source, export returns
`{"ok": false, "error": "..."}` and exits 1.

Export uses the stored filename's basename only. Absolute stored names and
`..` segments are rejected so the file cannot escape the chosen directory.

Export writes to disk and may create parent directories. Choose the destination
carefully.

## Python API

```python
from vera_doc import VeraDocument
from vera_ingest.viewer import export_source_document, get_source_document

doc = VeraDocument.open("manual.vera")
try:
    info = doc.inspect()  # always includes `ocr` when convert wrote it
    report = doc.validate()

    source = get_source_document(doc)
    print(source.filename, source.media_type, source.checksum)

    output = export_source_document(doc, "./exports")
    print(output)
finally:
    doc.close()
```

`source.data` contains the original bytes. `get_source_document()` and
`export_source_document()` raise `ValueError` when no original source is
stored.

## Recovery guidance

Validation identifies damage but does not repair an archive. The safest
recovery is:

1. preserve the failing archive for diagnosis;
2. verify that the source file (PDF, Markdown, or Office/HTML) is available;
3. convert the source into a new output path;
4. validate the new archive;
5. replace the old archive only after confirming search behavior.

Do not edit the SQLite tables directly as a routine repair strategy.
