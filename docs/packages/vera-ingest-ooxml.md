# vera-ingest-ooxml

Default Office ingest pipeline for VERA. It registers provider `ooxml` and
converts `.docx`, `.pptx`, and `.xlsx` with `python-docx`, `python-pptx`, and
`openpyxl`. It ships with the CLI and the desktop app. Docling stays available
as `--parser docling` when you want its higher-fidelity layout path.

See [Additional source formats and visual grounding](../multi-format-ingest.md)
for locator rules. Nothing here changes the `.vera` **0.2** schema.

## What it stores

The original Office file stays in `source_original`. A preview is written as
attachment `viewer_preview`:

| Format | Search chunks | Region kind | Preview |
|---|---|---|---|
| Word | headings, lists, and GFM tables, one logical page | `text_span` on the stored Markdown | `text/markdown` |
| PowerPoint | one page per slide, including speaker notes and pictures | `slide` (`slide`, `shape_index`) | `application/vnd.vera.slides+json` |
| Excel | one table chunk per row group, header repeated | `sheet_range` (`sheet`, `range` such as `Budget!A1:B3`) | `application/vnd.vera.sheets+json` |

Slide and sheet previews are native JSON, not Markdown. The desktop viewer
highlights Word with the Markdown preview, slides by block, and sheet cells by
A1 range. A cited sheet range past the preview cap is labeled as beyond the
preview. Empty workbooks fail with the same “No searchable text” error as an
empty Markdown file. A Word file that is corrupt, encrypted, or has no
searchable text fails the same way. When the package opens, one unreadable
paragraph or table is skipped, recorded in archive metadata
`ingest_warnings`, and the rest is searched. The Convert panel lists those
files as converted with warnings. Headers, footers, footnotes, endnotes,
comments, block content controls, text boxes, embedded documents, and charts
are left out of search by design. They are recorded as one plain sentence in
`ingest_notes`, not as a warning.

```bash
vera convert memo.docx memo.vera --json
vera convert deck.pptx deck.vera --json
vera convert budget.xlsx budget.vera --json
vera convert budget.xlsx --parser docling --json
```

Options: `chunk_size` (default 500 words), `overlap` (default 75),
`rows_per_chunk` (default 40), and `include_notes` (default true). OCR keys are
ignored so a mixed-folder convert can reuse one options bag.
