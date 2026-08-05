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

Python 3.10 or newer is required. First conversion may download Docling model
artifacts. Set `DOCLING_ARTIFACTS_PATH` to a local cache (or prefetch models
offline) for air-gapped runs.

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

- `--chunk-size` maps to HybridChunker's token limit. Docling's native
  merge/split strategy does **not** apply VERA's sliding-window `--overlap`.
- OCR modes map to Docling/RapidOCR: `off`, `auto` (default), and `force`
  (full-page OCR).
- Partial or failed Docling conversions are rejected rather than publishing an
  incomplete archive.

See the [vera-ingest-docling documentation](https://dkylewillis.github.io/vera/packages/vera-ingest-docling/)
and [conversion guide](https://github.com/dkylewillis/vera/blob/main/docs/conversion.md).
