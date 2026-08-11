# vera-ingest-docling

Optional Docling ingest pipeline plugin for VERA. Install it beside `vera-ingest`
to register the `docling` provider under the `vera.ingest_pipelines` entry-point
group.

## Install

```bash
python -m pip install "vera-ingest-docling>=0.2.4"
```

From a repository checkout:

```bash
uv sync --extra docling
```

The package pins Docling to the current supported minor range with the
`rapidocr` extra (RapidOCR + `onnxruntime`) and pulls a larger machine-learning
stack (including Torch). Do not add it to base VERA installs unless you need
layout-aware Docling conversion.

## First-run models

Docling may download layout/OCR model artifacts on first conversion. For offline
or CI environments:

1. Prefetch models while network access is available.
2. Point `DOCLING_ARTIFACTS_PATH` at a local cache directory.
3. Run conversions with hub offline mode enabled after prefetch
   (`HF_HUB_OFFLINE=1`).

## Usage

```bash
vera convert "manual.pdf" "manual.vera" --parser docling
vera convert "manual.pdf" "manual.vera" --parser docling:hybrid
```

```python
from vera_ingest import convert

convert("manual.pdf", "manual.vera", parser="docling")
```

The default Docling variant is `hybrid`. Unknown variants fail before parsing.

## Behavior

- Parses PDFs with Docling's `DocumentConverter` (tables and picture crops on).
- Chunks with Docling `HybridChunker` and an explicit whitespace tokenizer so
  `chunk_size` maps to a token limit without downloading a HuggingFace
  tokenizer.
- Owns typed defaults: `chunk_size=500` tokens, `ocr_mode=auto`,
  `ocr_language=en`, `pdf_backend=docling_parse`. Descriptor fields do **not**
  include `overlap` or `ocr_dpi`, so those legacy convert/CLI aliases are not
  forwarded.
- Stores readable chunk text for keyword search and contextualized text for
  embeddings.
- Maps provenance boxes from Docling bottom-left coordinates to VERA top-left
  page points.
- Attempts automatic recovery when Docling returns page-level memory errors
  (`bad_alloc`); rejects only when recovery is exhausted instead of publishing
  an incomplete archive.
- Maps VERA/Tesseract OCR language codes to RapidOCR (for example `eng` → `en`)
  before configuring Docling OCR.
- Disables Docling's `torch.compile` path so Windows conversions do not require
  Visual Studio's `cl.exe`, and keeps Docling's default `images_scale`.

## Reliability on large/complex PDFs

Docling's default `docling_parse` backend can hit native `std::bad_alloc` on
some large or complex pages. VERA recovers automatically:

1. Convert the whole document with the selected `pdf_backend` (default
   `docling_parse`).
2. On `PARTIAL_SUCCESS` with page-attributable memory errors, retry each failed
   page with a **fresh** converter (`page_range=(n, n)`), still on
   `docling_parse`.
3. If a single-page retry still fails, retry that page once with `pypdfium2`.
4. If too many pages fail (more than 20% of the document) or `convert()` raises,
   reconvert the **whole** document once with `pypdfium2`.
5. If recovery still cannot produce a complete result, conversion fails with a
   message that lists unrecoverable pages.

Force the low-memory backend for an entire conversion:

```bash
vera convert "manual.pdf" --parser docling --pipeline-option pdf_backend=pypdfium2
```

Successful recoveries are recorded in ingest diagnostics (surfaced by
`vera inspect`): `pdf_backend`, `recovered_pages`,
`recovered_pages_backend`, and optionally `whole_document_fallback_backend`.
`pypdfium2` is faster and more memory-stable but can reduce table/layout
fidelity compared with `docling_parse`.

## Desktop app

Source-run desktop conversions can select installed pipelines in the Convert
view when this package is present in the sidecar Python environment. Convert
controls are schema-driven from Docling's pipeline descriptor
(`describe_ingest_pipelines` / `PipelineConfigForm`), so overlap and OCR DPI
controls are not shown. Packaged desktop releases do **not** install or bundle
Docling plugins in this milestone.

## See also

- [Convert documents](../conversion.md)
- [vera-ingest package](vera-ingest.md)
- [ROADMAP](https://github.com/dkylewillis/vera/blob/main/ROADMAP.md)
