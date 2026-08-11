# vera-ingest-pymupdf

Default PyMuPDF ingest pipeline plugin for VERA. Install it beside
`vera-ingest` to register the `pymupdf` provider under the
`vera.ingest_pipelines` entry-point group.

`vera-cli` and `vera-app` depend on this package so PDF conversion works out
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
```

```python
from vera_ingest import convert

convert("manual.pdf", "manual.vera", parser="pymupdf")
```

## Behavior

- Parses PDFs with PyMuPDF; extracts bordered tables with pdfplumber.
- Selectively OCRs image-dominant low-text pages (`ocr_mode=auto`), with
  `force` for full-page OCR and `off` to disable OCR.
- Owns typed defaults: `chunk_size=500`, `overlap=75`, `ocr_mode=auto`,
  `ocr_language=eng`, `ocr_dpi=300`.
- Sliding-window chunking with heading detection produces searchable text and
  figure metadata.
- OCR is designed for scanned prose and does not reconstruct complex scanned
  forms or tables.

## Desktop app

Packaged and source-run desktop conversions use this pipeline by default.
Convert controls are schema-driven from the pipeline descriptor
(`describe_ingest_pipelines` / `PipelineConfigForm`). The sidecar build
bundles the English tessdata directory from this package.

## See also

- [Convert documents](../conversion.md)
- [Creating an ingest pipeline plugin](../creating-an-ingest-pipeline.md) — this
  package is the recommended starting reference.
- [vera-ingest](vera-ingest.md)
- [vera-ingest-docling](vera-ingest-docling.md)
