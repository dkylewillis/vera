# vera-lab

`vera-lab` is a **contributor tool** for inspecting ingest pipeline layout. It
runs a pipeline (or opens an existing `.vera` archive) and writes a single
self-contained HTML report with:

- page images rasterized from the source PDF;
- toggleable overlays for blocks, chunks, and figures;
- a linked inspector for chunk text, `block_ids`, and captions;
- convert-invariant and layout lint findings;
- stats (block types, token histogram, chunk linkage).

It is **not** part of the shipped CLI, MCP server, or desktop app. Install it
only in a development environment (the workspace `dev` extra).

## Install

From a repository checkout:

```bash
uv sync --extra dev
```

## Usage

```bash
# Live pipeline — no embeddings, no archive write
vera-lab manual.pdf -o report.html --parser pymupdf
vera-lab manual.pdf -o report.html --parser docling --pipeline-option ocr_mode=off

# Compare parsers (sidebar switcher + stats diff)
vera-lab manual.pdf -o compare.html --parser pymupdf --parser docling

# Inspect a written archive (requires an embedded source PDF)
vera-lab manual.vera -o archive.html
```

Useful flags:

| Flag | Purpose |
|------|---------|
| `--parser SPEC` | Ingest pipeline `provider[:variant]` (repeat to compare) |
| `--pipeline-option KEY=VALUE` | Provider-owned settings (repeatable) |
| `--dpi N` | Page rasterization DPI (default 96) |
| `--pages 1-5,8` | Page selection |
| `--max-pages N` | Cap rasterized pages (default 25) |

Open the HTML file in a browser. Use the Blocks / Chunks / Figures checkboxes
and click an overlay or list row to inspect details.

## What the lint checks

**Convert invariants** (same rules as shared `convert()`, but all findings are
reported instead of raising on the first):

- empty or duplicate block / chunk IDs;
- chunk `block_ids` that do not exist;
- empty chunk text.

**Layout lint** (silent bugs convert does not catch):

- image blocks not linked to any chunk (`--figures` will omit them);
- non-heading blocks covered by zero chunks;
- text blocks without a bbox (no highlight region after convert);
- table blocks whose text never reaches a chunk;
- caption blocks with no figure on the same page;
- chunks that span pages;
- zero-area or heavily overlapping bboxes.

## Python API

```python
from vera_lab import build_report

build_report("manual.pdf", "report.html", parsers=["pymupdf", "docling"])
build_report("manual.vera", "archive.html")
```

## Package boundaries

`vera-lab` depends on `vera-ingest` and PyMuPDF. Nothing in the release path
depends on it. It is named `vera-lab` (not `vera-ingest-lab`) because it is a
consumer of pipelines, not a pipeline provider under `vera.ingest_pipelines`.

## See also

- [Creating an ingest pipeline plugin](../creating-an-ingest-pipeline.md)
- [Figures and highlight regions](../figures-and-regions.md)
- [Architecture](../architecture.md)
