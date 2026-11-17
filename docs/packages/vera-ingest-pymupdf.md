# vera-ingest-pymupdf

Default PyMuPDF ingest pipeline plugin for VERA. Install it beside
`vera-ingest` to register the `pymupdf` provider under the
`vera.ingest_pipelines` entry-point group.

`vera` and `vera-app` depend on this package so PDF conversion works out
of the box.

## Install

```bash
python -m pip install "vera-ingest-pymupdf>=0.3.0"
```

From a repository checkout with uv, the workspace installs it by default:

```bash
uv sync
```

The package depends on PyMuPDF and pdfplumber. English OCR works offline with
the bundled `eng.traineddata`. Other Tesseract languages can be installed
manually via `TESSDATA_PREFIX` or fetched on demand with
`--ocr-allow-download` / `vera ocr-languages download`.

## Usage

```bash
vera convert "manual.pdf" "manual.vera"
vera convert "manual.pdf" "manual.vera" --parser pymupdf
vera convert "plans.pdf" "plans.vera" --parser pymupdf:plans
```

```python
from vera_ingest import convert

convert("manual.pdf", "manual.vera", parser="pymupdf")
```

## Behavior

- Parses PDFs with PyMuPDF; extracts bordered tables with pdfplumber.
- Selectively OCRs image-dominant low-text pages (`ocr_mode=auto`), with
  `force` for full-page OCR and `off` to disable OCR. Auto mode still OCRs a
  large-image page whose only native text is sparse (fewer than 200
  alphanumeric characters: headers, Bates stamps, letterhead). Blank pages
  and ordinary text pages skip OCR.
- Owns typed defaults: `chunk_size=500` whitespace-split words, `overlap=75`
  words, `ocr_mode=auto`, `ocr_language=eng`, `ocr_dpi=300`.
- `--parser pymupdf:plans` is a variant for construction drawing sets. It
  adds `ocr_drawn_text` (`auto` default, or `off`): auto mode also OCRs
  low-text drawing sheets (vector lettering, or several pasted images),
  keeps the real text layer, and adds only recognized words that do not
  already overlap it. It also puts each heading in the first chunk under it
  and stores a heading with no body as its own chunk, so detail titles are
  searchable. The default `pymupdf` pipeline does neither and rejects
  `ocr_drawn_text`. The variant is never selected by file extension and
  records `parser_name` `pymupdf:plans`.
- Sliding-window chunking with heading detection produces searchable text and
  figure metadata. Size and overlap count `str.split()` words, not characters
  or LLM subword tokens. Runtime overlap is clamped to `chunk_size - 1`.
- OCR is designed for scanned prose and does not reconstruct complex scanned
  forms or tables.
- Convert records diagnostics on archive metadata `ocr`: `ocr_engine`
  (`tesseract`), `ocr_mode`, `ocr_language`, `ocr_dpi`, `ocr_pages`
  (1-based pages that actually ran Tesseract). `pymupdf:plans` adds
  `ocr_drawn_text` and `ocr_drawn_text_pages` (the subset OCR'd because the
  lettering was drawn or pasted rather than a full-page scan). Read them with
  `vera inspect FILE --json`; text-mode inspect omits the bag.

## Desktop app

Packaged and source-run desktop conversions use this pipeline by default.
Convert controls are schema-driven from the pipeline descriptor
(`describe_ingest_pipelines` / `PipelineConfigForm`). The sidecar build
bundles the English tessdata directory from this package and copies package
metadata for entry-point discovery; importing the package also calls
`ensure_registered()` so PyInstaller freezes still resolve `pymupdf` when
dist-info is missing.

## See also

- [Convert documents](../conversion.md)
- [Creating an ingest pipeline plugin](../creating-an-ingest-pipeline.md) — this
  package is the recommended starting reference.
- [vera-ingest](vera-ingest.md)
- [vera-ingest-docling](vera-ingest-docling.md)
