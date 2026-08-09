# vera-ingest-docling

Optional Docling ingest pipeline for VERA. Registers the `docling` provider
(default variant `hybrid`) under the `vera.ingest_pipelines` entry-point group.

The pipeline uses Docling's `DocumentConverter` for layout-aware PDF parsing and
`HybridChunker` for token-aware chunks. Readable chunk text is stored for
keyword search; contextualized text from `HybridChunker.contextualize()` is used
for embeddings.

## Install

```bash
python -m pip install "vera-ingest-docling>=0.2.4"
```

From a repository checkout with uv:

```bash
uv sync --extra docling
```

Python 3.10 or newer is required. The package depends on Docling's `rapidocr`
extra so RapidOCR and `onnxruntime` are installed for OCR. First conversion may
download Docling model artifacts. Set `DOCLING_ARTIFACTS_PATH` to a local cache
(or prefetch models offline) for air-gapped runs.

This package is **not** bundled with the packaged desktop application. Source-run
desktop conversions can use it when the optional package is installed in the
sidecar Python environment.

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

- Defaults: `chunk_size=500` tokens, `ocr_mode=auto`, `ocr_language=en`.
  Docling does **not** advertise `overlap` or `ocr_dpi`, so those legacy
  convert/CLI aliases are not forwarded.
- Prefer `pipeline_options=` / `--pipeline-option KEY=VALUE` for provider-owned
  settings; `--chunk-size` and `--ocr*` remain compatibility aliases.
- OCR modes map to Docling/RapidOCR: `off`, `auto` (default), and `force`
  (full-page OCR). Tesseract-style codes such as `eng` are mapped to RapidOCR
  `en`.
- Torch model compilation is disabled so Windows does not need MSVC `cl.exe`.
- Partial or failed Docling conversions are rejected rather than publishing an
  incomplete archive.

See the [vera-ingest-docling documentation](https://dkylewillis.github.io/vera/packages/vera-ingest-docling/)
and [conversion guide](https://github.com/dkylewillis/vera/blob/main/docs/conversion.md).
