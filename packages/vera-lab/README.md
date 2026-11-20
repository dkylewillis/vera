# vera-lab

Contributor tool for inspecting ingest pipeline output. Run a pipeline (or open
an existing `.vera` archive) and emit a self-contained HTML report with page
images, typed block/chunk/figure overlays, layout lint, and stats.

This package depends on `vera-ingest` and PyMuPDF. `vera-app` depends on it,
and the packaged sidecar includes it. Desktop **Layout report** writes an
archive report under the folder from **Settings → Layout lab**, keeping the
archive's own folders. The `vera-lab` command is still installed with the
workspace `dev` extra.

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

Open the HTML file in a browser. The page and the side pane scroll separately.
The side pane shows archive metadata, then the selected record. Clicking a
detail, block, or figure shows that record's title, type, description, and
the blocks inside it. Toggle Blocks / Chunks / Figures layers to hide overlays.

Constraints: live mode does not write embeddings or an archive; archive mode
needs an embedded source PDF (`--store-original` defaults to true);
`--parser` is ignored for `.vera` inputs. Success prints the HTML path and
exit 0; failures print `vera-lab: ...` to stderr and exit 1.

## API

```python
from vera_lab import build_report

path = build_report("manual.pdf", "report.html", parsers=["pymupdf"])
```

See [docs/packages/vera-lab.md](../../docs/packages/vera-lab.md).
