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
  `ocr_language=en`. Descriptor fields do **not** include `overlap` or
  `ocr_dpi`, so those legacy convert/CLI aliases are not forwarded.
- Stores readable chunk text for keyword search and contextualized text for
  embeddings.
- Maps provenance boxes from Docling bottom-left coordinates to VERA top-left
  page points.
- Rejects Docling failure and partial-success results instead of publishing an
  incomplete archive.
- Maps VERA/Tesseract OCR language codes to RapidOCR (for example `eng` → `en`)
  before configuring Docling OCR.
- Disables Docling's `torch.compile` path so Windows conversions do not require
  Visual Studio's `cl.exe`, and keeps Docling's default `images_scale`.

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
