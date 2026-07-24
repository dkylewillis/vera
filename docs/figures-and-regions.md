# Figures and highlight regions

VERA stores extracted images, nearby captions, page dimensions, layout blocks,
and chunk-to-block mappings. These support figure-aware search and visual
grounding without reparsing the PDF.

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

Retrieve figures for a result:

```python
from vera import VeraDocument

doc = VeraDocument.open("manual.vera")
try:
    result = doc.search("pipe sizing chart", top_k=1)[0]
    figures = doc.figures_for(result)
    regions = doc.regions_for(result)
finally:
    doc.close()
```

Request image bytes when needed:

```python
doc = VeraDocument.open("manual.vera")
try:
    result = doc.search("pipe sizing chart", top_k=1)[0]
    figures = doc.figures_for(result, include_data=True)
    image_bytes = figures[0]["data"]
finally:
    doc.close()
```

Retrieve a stored asset directly:

```python
doc = VeraDocument.open("manual.vera")
try:
    asset = doc.get_asset("asset_block_000371", include_data=True)
finally:
    doc.close()
```

Retrieve regions by chunk ID:

```python
doc = VeraDocument.open("manual.vera")
try:
    regions = doc.get_chunk_regions("chunk_0042")
finally:
    doc.close()
```

For corpus results, use `VeraCorpus.figures_for(result)` and
`VeraCorpus.regions_for(result)`; the corpus dispatches to the correct archive.

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
