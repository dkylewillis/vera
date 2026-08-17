# vera-ingest-docling

Optional Docling ingest pipeline for VERA. Registers the `docling` provider
(default variant `hybrid`) under the `vera.ingest_pipelines` entry-point group.

The pipeline uses Docling's `DocumentConverter` for layout-aware PDF parsing and
`HybridChunker` for token-aware chunks. Readable chunk text is stored for
keyword search; contextualized text from `HybridChunker.contextualize()` is used
for embeddings.

## Install

```bash
python -m pip install "vera-ingest-docling>=0.3.0"
```

From a repository checkout with uv (workspace `.venv` for CLI/tests/`app:dev`):

```bash
uv sync --extra docling
```

Non-desktop users can install the CLI extra:

```bash
pip install "vera-cli[docling]>=0.3.0"
```

Python 3.10 or newer is required. The package depends on Docling's `rapidocr`
extra so RapidOCR and `onnxruntime` are installed for OCR. First conversion may
download Docling model artifacts. Set `DOCLING_ARTIFACTS_PATH` to a local cache
(or prefetch models offline) for air-gapped runs. The desktop app uses an
app-owned cache under Electron `userData`.

The packaged Windows sidecar freezes this pipeline as **Advanced layout
(slower)** beside PyMuPDF.

## Usage

```bash
vera convert "manual.pdf" "manual.vera" --parser docling
# or explicitly:
vera convert "manual.pdf" "manual.vera" --parser docling:hybrid
```

```python
from vera_ingest import convert

convert("manual.pdf", "manual.vera", parser="docling")
```

## Notes

- Defaults: `chunk_size=500` whitespace tokens (not LLM subword tokens),
  `ocr_mode=auto`, `ocr_language=en`,
  `pdf_backend=docling_parse`. Docling does **not** advertise `overlap` or
  `ocr_dpi`, so those legacy convert/CLI aliases are not forwarded. The
  Tesseract `--ocr-language` alias is also not forwarded; Docling keeps `en`.
- Prefer `pipeline_options=` / `--pipeline-option KEY=VALUE` for provider-owned
  settings; `--chunk-size` and `--ocr*` remain compatibility aliases for
  pipelines that accept them.
- OCR modes map to Docling/RapidOCR: `off`, `auto` (default), and `force`
  (full-page OCR). `ocr_language` expects a RapidOCR-native code (`en`, `fr`,
  `cyrillic`, ...) — Tesseract-style codes such as `eng` are **not**
  translated. The shared `--ocr-language` CLI default (`eng`) is not
  forwarded; pass `--pipeline-option ocr_language=fr` (or another RapidOCR
  code) when you need a non-default language.
- Torch model compilation is disabled so Windows does not need MSVC `cl.exe`.
- Picture crops are stored as figure attachments and linked onto a nearby
  same-page chunk so search `--figures` can return them. Docling's
  HybridChunker omits pictures from chunk text.
- On page-level memory errors (`bad_alloc`), VERA retries failed pages then
  falls back to `pypdfium2`; force that backend with
  `--pipeline-option pdf_backend=pypdfium2`. Conversion rejects only when
  recovery is exhausted.

See the [vera-ingest-docling documentation](https://dkylewillis.github.io/vera/packages/vera-ingest-docling/)
and [conversion guide](https://github.com/dkylewillis/vera/blob/main/docs/conversion.md).
