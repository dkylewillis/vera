# Figures and highlight regions

VERA stores extracted images, nearby captions, page dimensions, layout blocks,
and chunk-to-block mappings. These support figure-aware search and visual
grounding without reparsing the PDF.

## Storage map (VERA 0.2 schema)

`vera-doc` has no dedicated `figures`, `tables`, `regions`, `blocks`, or
`pages` tables. Conversion (`vera-ingest`) writes those concepts as JSON and
opaque attachments into the standard 0.2 tables. Viewer helpers under
`vera_ingest.viewer` interpret the conventions below.

| Item | Table | Column / location |
|---|---|---|
| Chunk text (including table markdown) | `chunks` | `text` |
| Citations (`page_start`, `page_end`, `heading_path`, `source_filename`, …) | `chunks` | `metadata_json` |
| Highlight regions / text bounding boxes | `chunks` | `metadata_json` → `"regions"` |
| Figure image bytes | `attachments` | `data` (row id like `image_block_000042`) |
| Figure mime type and filename | `attachments` | `mime_type`, `filename` |
| Figure role, page, and bbox | `attachments` | `metadata_json` → `"role": "figure"`, `"page_number"`, `"bbox"` |
| Chunk ↔ figure link | `chunk_attachments` | `chunk_id`, `attachment_id`, `role` (`"figure"`) |
| Chunk ↔ source PDF link | `chunk_attachments` | `chunk_id`, `attachment_id`, `role` (`"source"`) |
| Page dimensions and page text | `attachments` | `viewer_pages` row; JSON payload in `data` |
| Full layout blocks (heading, paragraph, table, caption, image, …) | `attachments` | `viewer_blocks` row; JSON payload in `data` |
| Original source PDF (optional) | `attachments` | `source_original` row; PDF bytes in `data` |
| Pointers to viewer/source attachments | `vera_metadata` | `archive_metadata` JSON → `viewer_pages_attachment_id`, `viewer_blocks_attachment_id`, `source_attachment_id` |

How to read the map:

- **Tables** are not separate attachment types. Selectable tables become chunk
  `text` (markdown) and a `block_type: "table"` entry inside `viewer_blocks`.
  Their bbox is included in chunk `regions` like other non-image blocks.
- **Captions** live in `viewer_blocks` as `block_type: "caption"` and usually
  also as searchable chunk text. The figure API joins a caption by page number.
- **Image blocks** are excluded from chunk `regions` and surfaced through
  figure attachments instead.
- Coordinate contract for every `bbox`: `[x0, y0, x1, y1]` in page points,
  origin top-left. See [Coordinate conversion](#coordinate-conversion).

See [Format specification (0.2)](vera-spec-v0.2.md) for the table definitions
themselves.

## Include figures in search results

`--figures` affects JSON output:

```bash
vera search "manual.vera" "pipe sizing chart" --figures --json
```

Each search result gains a `figures` array. A figure includes:

- `block_id`
- `page_number`
- `bbox`
- `page_width` and `page_height`
- `asset_id`
- `mime_type`
- `filename`
- `caption`

The CLI returns metadata and captions, not image bytes.

VERA first returns figures directly associated with the result's source blocks.
For older archives without that association, it falls back to figures on the
result's page range.

Captions are detected from nearby caption blocks. A missing caption is returned
as `null`; do not infer one from unrelated page text.

## Include text highlight regions

`--regions` also affects JSON output:

```bash
vera search "manual.vera" "detention requirements" --regions --json
```

Each result gains a `regions` array:

```json
{
  "block_id": "block_0042",
  "page_number": 117,
  "bbox": [72.0, 430.0, 540.0, 510.0],
  "page_width": 612.0,
  "page_height": 792.0
}
```

`bbox` is `[x0, y0, x1, y1]` in page points with the origin at the top-left.
Use the returned page dimensions to scale coordinates to a rendered page.

Regions are block-granular. When a chunk starts or ends in the middle of a
block, the region covers the whole contributing block. Image blocks are
excluded from text regions and are returned through the figure API instead.

## Coordinate conversion

For a rendered page of width `rendered_width` and height `rendered_height`:

```text
scale_x = rendered_width / page_width
scale_y = rendered_height / page_height

left   = x0 * scale_x
top    = y0 * scale_y
width  = (x1 - x0) * scale_x
height = (y1 - y0) * scale_y
```

Renderers that use a bottom-left coordinate origin must flip the vertical
coordinates using `page_height`.

## Python API

Viewer helpers live in `vera_ingest.viewer`. They interpret the attachment and
metadata conventions written by conversion; `vera-doc` stores those values
opaquely.

Retrieve figures for a result:

```python
from vera_doc import VeraDocument
from vera_ingest.viewer import figures_for, regions_for

doc = VeraDocument.open("manual.vera")
try:
    result = doc.search("pipe sizing chart", top_k=1)[0]
    figures = figures_for(doc, result)
    regions = regions_for(doc, result)
finally:
    doc.close()
```

Request image bytes when needed:

```python
from vera_ingest.viewer import figures_for

doc = VeraDocument.open("manual.vera")
try:
    result = doc.search("pipe sizing chart", top_k=1)[0]
    figures = figures_for(doc, result, include_data=True)
    image_bytes = figures[0]["data"]
finally:
    doc.close()
```

Retrieve a figure attachment directly:

```python
doc = VeraDocument.open("manual.vera")
try:
    attachment = doc.get_attachment("image_block_000371")
finally:
    doc.close()
```

Retrieve regions by chunk ID:

```python
from vera_ingest.viewer import get_chunk_regions

doc = VeraDocument.open("manual.vera")
try:
    regions = get_chunk_regions(doc, "chunk_0042")
finally:
    doc.close()
```

For corpus results, resolve the archive first:

```python
from vera_ingest.viewer import figures_for, regions_for

figures = figures_for(corpus.document(result.file), result)
regions = regions_for(corpus.document(result.file), result)
```

## MCP tools

MCP clients can use:

- `vera_search` with `include_figures` or `include_regions`;
- `vera_figures` to list figures in an optional page range;
- `vera_get_chunk_regions` to resolve one chunk ID.

See [MCP integration](mcp.md).

## Limitations

- Figure metadata does not imply that the pixels were visually interpreted.
- Captions depend on PDF layout extraction and proximity.
- Tables represented as selectable text may be text blocks rather than image
  assets.
- Regions identify source blocks, not individual words or characters.
- Convert and the desktop source viewer are PDF-only today. Planned
  Markdown previews for flow documents, typed region `kind` values, and
  later sheet/slide locators are in
  [Additional source formats and visual grounding](multi-format-ingest.md).
  Those locators stay in chunk metadata; they do not change format 0.2.
