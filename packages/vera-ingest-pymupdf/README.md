# vera-ingest-pymupdf

Default PyMuPDF ingest pipeline for VERA. Registers the `pymupdf` provider under
the `vera.ingest_pipelines` entry-point group.

The pipeline uses PyMuPDF for PDF parsing, pdfplumber for bordered tables, and
optional Tesseract OCR (English language data is bundled). Sliding-window
chunking with heading detection produces searchable text chunks and figure
metadata.

## Install

```bash
python -m pip install "vera-ingest-pymupdf>=0.3.0"
```

From a repository checkout with uv, the workspace installs this package by
default (via `vera-cli` / `vera-app`). You can also install it directly:

```bash
uv sync
# or explicitly:
python -m pip install ./packages/vera-doc ./packages/vera-ingest ./packages/vera-ingest-pymupdf
```

Python 3.10 or newer is required. English OCR works offline with the bundled
`eng.traineddata`. Other Tesseract languages can be installed manually via
`TESSDATA_PREFIX` or fetched on demand with `--ocr-allow-download` /
`vera ocr-languages download`.

## Usage

```bash
vera convert "manual.pdf" "manual.vera"
# or explicitly:
vera convert "manual.pdf" "manual.vera" --parser pymupdf
```

```python
from vera_ingest import convert

convert("manual.pdf", "manual.vera", parser="pymupdf")
```

## Notes

- Defaults: `chunk_size=500` whitespace-split words, `overlap=75` words,
  `ocr_mode=auto`, `ocr_language=eng`, `ocr_dpi=300`.
- Prefer `pipeline_options=` / `--pipeline-option KEY=VALUE` for provider-owned
  settings; `--chunk-size`, `--overlap`, and `--ocr*` remain compatibility
  aliases.
- Selective OCR (`auto`) OCRs image-dominant low-text pages, including scans
  whose only native text is a header, Bates stamp, or letterhead (fewer than
  200 alphanumeric characters on a large-image page). Use `force` for
  full-page OCR or `off` to disable OCR.

See the [vera-ingest-pymupdf documentation](https://dkylewillis.github.io/vera/packages/vera-ingest-pymupdf/)
and [conversion guide](https://github.com/dkylewillis/vera/blob/main/docs/conversion.md).
