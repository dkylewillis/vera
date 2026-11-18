# vera-ingest-plans

An optional VERA ingest pipeline plugin for construction drawing sets. It
registers the `plans` provider under the `vera.ingest_pipelines` entry-point
group.

`plans` runs the default PyMuPDF parser with two changes:

- It also OCRs low-text sheets whose lettering is drawn as linework or pasted
  as several images (`ocr_drawn_text`, default `auto`). Real text stays; OCR
  only adds the missing words.
- It keeps heading text (detail titles) in each chunk's body so a title such as
  "SADDLE BLOCKING" is searchable.

The desktop installer and the default `vera` install do not include it.

## Install

CLI, in the same environment as `vera` (it is not published to PyPI). From a
checkout, `uv sync --extra plans` does the same:

```bash
pip install ./packages/vera-ingest-plans
vera convert plans.pdf plans.vera --parser plans --json
vera library pipeline ./library --folder "Projects/*/Plans" --parser plans --json
```

Desktop app: build the wheel, then choose **Settings > Plugins > Install from
file** and pick it. VERA restarts its converter so `plans` appears in Convert
and in the folder pipeline picker.

```bash
uv build --package vera-ingest-plans --out-dir dist
```

The wheel is pure Python and only imports `vera-ingest` and
`vera-ingest-pymupdf`, which the desktop app already ships.
