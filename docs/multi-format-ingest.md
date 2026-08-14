# Additional source formats and visual grounding

**Status:** planned after 0.3.0. Convert, batch discovery, and the desktop
source viewer are PDF-only today. This page records the intended direction so
plugin naming, locators, and viewers stay consistent when non-PDF ingest
lands.

See the [roadmap](https://github.com/dkylewillis/vera/blob/main/ROADMAP.md)
for the checklist. Nothing here changes the `.vera` **0.2** schema.

## Plugin naming

Name ingest packages after the **engine**, not the file type:

- `vera-ingest-pymupdf` registers provider `pymupdf`
- `vera-ingest-docling` registers provider `docling`

`--parser` / `parser=` is `provider[:variant]`. The PyPI name is only how the
plugin is installed. Two packages conflict only if they register the same
provider under `vera.ingest_pipelines`.

Do **not** ship `vera-ingest-docling-pdf` (or `docling-docx`). When Docling
gains formats, expand the existing package and advertise them on the
descriptor. Variants (`docling:hybrid`) stay processing strategies, not file
types. Two engines may both handle PDF; the user picks `--parser`.

`PipelineCapabilities.source_formats` is the metadata slot for “what this
plugin can ingest” (the example pipeline already sets `("txt",)`; first-party
pipelines currently default to `("pdf",)`). Convert, batch discovery, and
file pickers should consult that list instead of hardcoding `.pdf`.

## Two grounding surfaces

Visual grounding means highlighting the surface the user is looking at.
That surface is not the same for every format.

| Input | Searchable text | What to highlight |
|---|---|---|
| PDF | layout blocks, as today | original PDF + page bounding boxes |
| DOCX, HTML, Markdown, TXT | Markdown (or the file when it is already Markdown) | stored Markdown preview |
| CSV / small tables | Markdown or row text for retrieval | Markdown excerpt is acceptable; sheet+range is better later |
| Excel, PPTX | Markdown excerpts may be searchable | do not treat generated Markdown as the visual source of truth |

Keep today’s PDF overlay. Do not convert PDFs to Markdown in order to reuse
a Markdown viewer — that would drop page-accurate citations, scans, and
figures.

For flow documents, generate Markdown **at ingest**, store that exact
document as a viewer attachment, and highlight it. Re-deriving Markdown at
view time makes line numbers and wrapping drift. Keep `source_original` as
the real `.docx` / `.html` / `.md` bytes for export and reconvert. The
Markdown file is a viewer payload, in the same role `viewer_pages` plays for
PDFs.

Durable locators in that stored Markdown should be **block or heading
anchors** (`block_id` mapped to a heading or preview `id`). Line spans of
generated Markdown are a convenience, not a stable contract across reconvert.

Spreadsheets and slides are spatial. A 20k-row sheet as one GFM table is not
a viewer, and “line 40” is not `Sheet1!B4:D18` or “slide 7.” Retrieval may
still embed Markdown excerpts; visual grounding for those types is a later
native locator (`sheet_range`, slide + bbox), not this Markdown preview.

## Locators stay in chunk metadata

A hit is already `chunk → block_ids → locators`. Convert copies contributing
block locators onto `chunks.metadata_json.regions`. That JSON is conventional
in format 0.2: unknown keys MUST be preserved, and `vera validate` does not
require `page_number` or `bbox`.

When non-PDF locators land, add a `kind` on each region rather than new
tables:

```json
{ "kind": "page_bbox", "block_id": "block_0042",
  "page_number": 12, "bbox": [72, 144, 510, 220],
  "page_width": 612, "page_height": 792 }

{ "kind": "text_span", "block_id": "block_0008",
  "start": { "line": 40, "column": 1 },
  "end": { "line": 55, "column": 12 } }

{ "kind": "sheet_range", "block_id": "block_0010",
  "sheet": "Budget", "range": "B4:D18" }
```

Existing PDF archives without `kind` stay valid; viewers treat a missing
`kind` plus a bbox as `page_bbox`. `page_start` / `page_end` remain optional
citation fields for paginated sources — do not invent page 1 for a CSV.

`Citation` and the desktop viewer are software, not schema. The library index
copies `page_start` / `page_end` into nullable columns and does not copy
`regions`; corpus hits that need a Markdown span or cell range still read the
archive (or later index extra columns). Neither change is a format 0.2 bump.

## Desktop viewer

`PdfSourceViewer` stays the PDF overlay. A dispatcher chooses a surface from
source MIME (and archive metadata such as `source_mime_type`):

- `application/pdf` — current page + bbox overlay
- Markdown viewer attachment — heading/block highlight in the stored preview
- unknown — result text plus the citation string (already works)

Pipeline capabilities can later advertise both `source_formats` and which
grounding kinds the plugin emits.

## Non-goals

- Encoding the file type in the plugin package or provider name.
- Forcing every format through PDF page points.
- Bumping `format_version` for new locator shapes.
- Using generated Markdown as the highlight target for Excel or PowerPoint.
- Replacing PDF visual grounding with a Markdown conversion of the PDF.

## See also

- [Creating an ingest pipeline plugin](creating-an-ingest-pipeline.md) —
  registry, descriptors, and `source_formats`.
- [Figures and highlight regions](figures-and-regions.md) — current PDF
  overlay convention and 0.2 storage map.
- [Format specification (0.2)](vera-spec-v0.2.md) — chunk metadata is
  conventional JSON; readers preserve unknown keys.
- [Architecture](architecture.md) — `vera-doc` does not know source formats.
