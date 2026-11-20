# vera-lab

`vera-lab` is a **contributor tool** for inspecting ingest pipeline layout. It
runs a pipeline (or opens an existing `.vera` archive) and writes a single
self-contained HTML report with:

- page images rasterized from the source PDF;
- toggleable overlays for blocks, chunks, and figures;
- a linked inspector for chunk text, `block_ids`, and captions;
- convert-invariant and layout lint findings;
- stats (block types, token histogram, chunk linkage).

The desktop app depends on this package. Right-click a converted document,
choose **Layout report**, and the HTML is written under the folder in
**Settings → Layout lab**, keeping the archive's own folders so two files
with the same name stay apart. The packaged sidecar includes `vera-lab`.
The `vera` command does not include a lab subcommand. The `vera-lab` command
remains for a development checkout.

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

From the desktop app, set **Settings → Layout lab** to a folder, then right-click
a converted document and choose **Layout report**. The app writes
`manual.pdf.lab.html` under that folder, keeping the archive's own folders
(`Plans/North/manual.pdf.vera` stays separate from `Plans/South/manual.pdf.vera`),
replaces an existing file of that name, and opens it. It rasterizes at most
200 pages. The packaged app includes vera-lab.

Useful flags:

| Flag | Purpose |
|------|---------|
| `--parser SPEC` | Ingest pipeline `provider[:variant]` (repeat to compare). Ignored for `.vera` archives. Default: `pymupdf` |
| `--pipeline-option KEY=VALUE` | Provider-owned settings (repeatable; live PDF mode only) |
| `-o` / `--output` | HTML path (default: `vera-lab-report.html`) |
| `--dpi N` | Page rasterization DPI (default 96) |
| `--pages 1-5,8` | Page selection |
| `--max-pages N` | Cap rasterized pages (default 25) |

Open the HTML file in a browser. The page images scroll on their own; the
archive facts, the selection, and the block, chunk, and figure lists stay in
the side pane and scroll separately. The facts include format, source,
embedding model, parser, chunking, OCR, and any record types stored on the
chunks. Use the Blocks / Chunks / Figures checkboxes and click an overlay or
list row. The selection shows that record's metadata — title, type,
description, sheet — and the blocks that sit inside it. Success prints the output path; failures
print `vera-lab: ...` to stderr and exit 1.

## Constraints

- Live PDF mode runs the selected pipeline only. It does not compute embeddings
  or write a `.vera` archive.
- Archive mode requires an embedded source PDF. Archives created with
  `--store-original false` fail with "Original source document is not stored
  in this archive".
- `--parser` is ignored for `.vera` inputs. Compare two pipelines by passing
  a PDF and repeating `--parser`.
- Rasterization stops at `--max-pages` (default 25) unless `--pages` names a
  smaller set. Large manuals need an explicit page range.

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

`vera-lab` depends on `vera-ingest` and PyMuPDF. `vera-app` depends on
`vera-lab`. It is named `vera-lab` (not `vera-ingest-lab`) because it is a
consumer of pipelines, not a pipeline provider under `vera.ingest_pipelines`.

## See also

- [Creating an ingest pipeline plugin](../creating-an-ingest-pipeline.md)
- [Figures and highlight regions](../figures-and-regions.md)
- [Architecture](../architecture.md)
