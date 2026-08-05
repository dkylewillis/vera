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

The package pins Docling to the current supported minor range and pulls a larger
machine-learning stack (including Torch). Do not add it to base VERA installs
unless you need layout-aware Docling conversion.

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
  `--chunk-size` maps to a token limit without downloading a HuggingFace
  tokenizer.
- Stores readable chunk text for keyword search and contextualized text for
  embeddings.
- Maps provenance boxes from Docling bottom-left coordinates to VERA top-left
  page points.
- Rejects Docling failure and partial-success results instead of publishing an
  incomplete archive.
- Records that VERA `--overlap` is not applied by Docling's native merge/split.

## Desktop app

Source-run desktop conversions can select installed pipelines in the Convert
view when this package is present in the sidecar Python environment. Packaged
desktop releases do **not** install or bundle Docling plugins in this milestone.

## See also

- [Convert documents](../conversion.md)
- [vera-ingest package](vera-ingest.md)
- [ROADMAP](https://github.com/dkylewillis/vera/blob/main/ROADMAP.md)
