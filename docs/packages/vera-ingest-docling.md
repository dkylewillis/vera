# vera-ingest-docling

Optional Docling ingest pipeline plugin for VERA. Install it beside `vera-ingest`
to register the `docling` provider under the `vera.ingest_pipelines` entry-point
group.

## Install

```bash
python -m pip install "vera-ingest-docling>=0.3.0"
```

From a repository checkout, `uv sync --extra docling` adds it to the
workspace `.venv` (CLI, tests, and `app:dev`). Non-desktop users can also:

```bash
pip install "vera-cli[docling]>=0.3.0"
```

The packaged Windows app already freezes this pipeline into the sidecar
as **Advanced layout (slower)**. That installer also includes Sentence
Transformers, MiniLM (`all-MiniLM-L6-v2`) weights, and Docling Heron ONNX
plus TableFormer accurate snapshots. CLI and source-run
installs still need `vera-doc[ml]` / `uv sync --extra ml` for neural
embeddings; those extras are independent of this Docling package.

The package pins Docling to the current supported minor range with the
`rapidocr` extra (RapidOCR + `onnxruntime`) and pulls a larger machine-learning
stack (including Torch). Do not add it to base VERA installs unless you need
layout-aware Docling conversion. Descriptor discovery does not import Docling;
if `docling` or `docling_core` is missing, Convert lists the pipeline as not
installed instead of failing plugin load.

## First-run models

Docling may download layout and table model artifacts on first conversion.
RapidOCR weights ship with `docling[rapidocr]` (and the desktop sidecar freeze);
VERA pins those packaged ONNX paths so setting `DOCLING_ARTIFACTS_PATH` does not
require a separate RapidOCR prefetch. VERA treats that artifacts directory as
offline only when both `docling-project--docling-layout-heron-onnx` (with
weights) and `docling-project--docling-models` (TableFormer accurate
`tm_config.json` and weights) are complete. A half-written folder stays online
so Hugging Face can resume.
The desktop app prefetches those models when you select Advanced layout
(`prepare_docling`) instead of waiting for the first PDF convert. Stopping
mid-download does not abort Hugging Face immediately; the next run resumes.
The first prefetch is about 380 MB (Heron ONNX + TableFormer accurate). Packaged
Windows builds vendor those snapshots in Setup.exe, so Advanced layout there
does not download them. Convert
uses the ONNX layout engine so the Transformers Heron snapshot is not required.
For other Docling models in offline
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
  Cropped pictures are stored as figure attachments and linked onto a nearby
  same-page chunk. Docling's HybridChunker omits pictures from chunk text
  (empty image placeholder), so that linking is what makes `--figures` work.
- Chunks with Docling `HybridChunker` and an explicit whitespace tokenizer so
  `chunk_size` maps to whitespace-split words without downloading a HuggingFace
  tokenizer.
- Owns typed defaults: `chunk_size=500` whitespace tokens, `ocr_mode=auto`,
  `ocr_language=en`, `pdf_backend=docling_parse`. Descriptor fields do **not**
  include `overlap` or `ocr_dpi`, so those legacy convert/CLI aliases are not
  forwarded. The Tesseract `--ocr-language` / `ocr_language` alias is also
  not forwarded (`capabilities.ocr_engine` is RapidOCR, not Tesseract).
- Stores readable chunk text for keyword search and contextualized text for
  embeddings.
- Maps provenance boxes from Docling bottom-left coordinates to VERA top-left
  page points.
- Attempts automatic recovery when Docling returns page-level memory errors
  (`bad_alloc`) or the whole-document convert raises; rejects only when
  recovery is exhausted instead of publishing an incomplete archive.
- `ocr_language` expects a RapidOCR-native code (for example `en`, `fr`,
  `cyrillic`); it is **not** translated from Tesseract-style codes, so
  PyMuPDF's `eng` is not valid here. The shared `--ocr-language` CLI default
  (`eng`) is not forwarded to this pipeline; Docling keeps `en` unless you
  pass `--pipeline-option ocr_language=...`.
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
5. If that whole-document convert raises or does not fully succeed, convert in
   page batches with `pypdfium2` (one reused converter) so peak memory stays
   bounded on large manuals.
6. If recovery still cannot produce a complete result, conversion fails with a
   message that includes the underlying exception. The sidecar also prints the
   traceback to stderr (`[vera-sidecar]` in `npm run app:dev`).

Force the low-memory backend for an entire conversion:

```bash
vera convert "manual.pdf" --parser docling --pipeline-option pdf_backend=pypdfium2
```

Successful recoveries are recorded in ingest diagnostics (surfaced by
`vera inspect`): `pdf_backend`, `recovered_pages`,
`recovered_pages_backend`, and optionally `whole_document_fallback_backend`
and `whole_document_fallback_strategy` (`document` or `batched`).
`pypdfium2` is faster and more memory-stable but can reduce table/layout
fidelity compared with `docling_parse`.

## Desktop app

Source-run and packaged desktop conversions list Docling as **Advanced layout
(slower)** beside PyMuPDF. Selecting that pipeline runs `prepare_docling`.
Packaged Windows builds already include Heron ONNX and TableFormer accurate;
`app:dev` prefetches them into the app-owned `DOCLING_ARTIFACTS_PATH` cache.
Convert controls are schema-driven
from Docling's pipeline descriptor (`describe_ingest_pipelines` /
`PipelineConfigForm`), so overlap and OCR DPI controls are not shown.

## See also

- [Convert documents](../conversion.md)
- [Creating an ingest pipeline plugin](../creating-an-ingest-pipeline.md) — this
  package demonstrates layout mapping and failure recovery beyond the basics.
- [Additional source formats and visual grounding](../multi-format-ingest.md) —
  grow formats inside this engine package; do not split into
  `vera-ingest-docling-pdf`.
- [vera-ingest package](vera-ingest.md)
- [ROADMAP](https://github.com/dkylewillis/vera/blob/main/ROADMAP.md)
