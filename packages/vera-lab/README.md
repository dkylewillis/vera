# vera-lab

Contributor tool for inspecting ingest pipeline output. Run a pipeline (or open
an existing `.vera` archive) and emit a self-contained HTML report with page
images, typed block/chunk/figure overlays, layout lint, and stats.

This package is a **dev leaf**: it depends on `vera-ingest` and PyMuPDF, and
nothing in the release path depends on it. Install it via the workspace `dev`
extra.

## Install

From a repository checkout:

```bash
uv sync --extra dev
```

## Usage

```bash
# Live pipeline (fast loop — no embeddings, no archive write)
vera-lab manual.pdf -o report.html --parser pymupdf
vera-lab manual.pdf -o report.html --parser docling --pipeline-option ocr_mode=off

# Compare parsers
vera-lab manual.pdf -o compare.html --parser pymupdf --parser docling

# Inspect a written archive
vera-lab manual.vera -o archive.html
```

Open the HTML file in a browser. Toggle Blocks / Chunks / Figures layers and
click overlays to inspect details.

## API

```python
from vera_lab import build_report

path = build_report("manual.pdf", "report.html", parsers=["pymupdf"])
```

See [docs/packages/vera-lab.md](../../docs/packages/vera-lab.md).
