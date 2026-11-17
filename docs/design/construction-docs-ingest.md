# Design: construction-document (plan set) ingest and enrichment

| | |
|---|---|
| **Status** | Proposed, ready to build |
| **Owner** | Kyle Willis |
| **Target packages** | new `vera-ingest-plansheet` (pipeline + enrichment), additions to `vera` (CLI), `vera-mcp` (tools), `vera-ingest.viewer` (helpers) |
| **Format impact** | None. Everything fits VERA 0.2 (chunk `metadata_json`, attachments, `archive_metadata`) |
| **Pilot corpus** | ISE `ISE_Assets\Construction Plans`, 502 plan sets, roughly 15,000–30,000 sheets |

This document is written so a coding agent can build it phase by phase. Every
phase ends with acceptance criteria. Section 2 records what the current code
actually does, because several decisions depend on it.

---

## 1. Purpose

Civil engineering firms hold hundreds of issued construction plan sets (PDF,
mostly CAD-printed vector output, some scanned). Today they can only be found
by folder browsing. Engineers routinely want to ask:

- "Show me Gwinnett County commercial sites under 5 acres with underground detention."
- "Find every **flume** detail we have drawn, with a thumbnail and a link to the sheet."
- "Which projects had a septic field and a retaining wall?"
- "How did we detail a riprap apron at a headwall last time?"

Goal: make plan sets searchable by **jurisdiction, size, development type,
site features, and detail types**, and make individual **details** findable as
cropped, cited figures across the whole archive.

Principles:

1. **Normal ingest stays fast.** Deterministic, CPU-only work runs at convert
   time. All VLM work is an optional, slow-path **enrichment** stage that runs
   later in the background.
2. **Local first.** The default VLM backend runs on the firm's own hardware.
   No drawing leaves the office unless the user opts in to a hosted backend.
   Privacy is VERA's differentiator against cloud products (Nomic, Curtis,
   Piramade, VitruAI, Tektome, SalemWise Corpus).
3. **Every claim is citable.** Every extracted item stores `page_number` and
   `bbox` in page points so the viewer can highlight it, exactly like today's
   chunk `regions`.
4. **Structured where you filter, free text where you understand.** Controlled
   vocabularies for type fields, free text for purpose.
5. **No format change.** Use VERA 0.2 conventions (spec §4, §5); the spec
   explicitly allows new locators and metadata keys without a `format_version`
   bump.

---

## 2. What the repo does today (findings that shape this design)

Verified against `main` (Nov 2026).

### 2.1 A pipeline plugin mechanism already exists

- Contract: `IngestPipeline = Callable[[str, IngestRequest], IngestResult]`
  (`vera_ingest.types`). See [Creating an ingest pipeline plugin](../creating-an-ingest-pipeline.md).
- Discovery: Python entry points `vera.ingest_pipelines` and
  `vera.ingest_pipeline_descriptors` (see `packages/vera-ingest-pymupdf/pyproject.toml`).
  Options are a `PipelineOptions` dataclass with `from_mapping`, and the
  descriptor drives `--pipeline-option KEY=VALUE` and the desktop Convert UI.
- `IngestResult` carries `pages`, `blocks` (`IngestBlock` with `block_type`,
  `bbox`, optional `image_bytes`), `chunks` (`IngestChunk` with free-form
  `metadata` dict and optional `embedding_text`), `diagnostics`, `warnings`, `notes`.
- Shared conversion (`vera_ingest.convert`) stores any block with
  `image_bytes` as a **figure attachment** (`role: "figure"`, `page_number`,
  `bbox`) and links it to chunks **only through `chunk.block_ids`**. Chunk
  `metadata` is merged into `chunks.metadata_json`.

**Consequence:** the new work is a normal pipeline plugin. No new plugin
system is needed for ingest. A second hook is needed for post-ingest
enrichment, which does not exist yet (section 5.4).

### 2.2 Figures are raster-only, which matters a lot for CAD plan sets

`vera-ingest-pymupdf` (`parser.py::_collect_raw_blocks`) creates image blocks
only from PyMuPDF `page.get_text("dict")` blocks of `type == 1`, meaning
**embedded raster images**. It drops images under 20 pt in both dimensions and
de-duplicates by SHA-256 (`pipeline.py::_drop_repeated_images`).
[Figures and regions](../figures-and-regions.md#limitations) already states:
"Vector drawings and decorative marks often have no figure attachment."

Expected behavior on plan sets:

| Sheet kind | What today's pipeline extracts as figures |
|---|---|
| CAD-printed vector detail sheet | Usually **no** per-detail figures. Maybe a raster logo, seal, or vicinity map. |
| Scanned sheet | **One full-page raster** figure (plus OCR text) |
| Hybrid (vector + pasted raster detail) | Only the pasted raster pieces |

Captions are detected with `_CAPTION_RE`
(`figure|fig.|table|diagram|exhibit|...` + number), which civil detail titles
such as `4  CONCRETE FLUME` / `SCALE: NTS` do not match.

Docling (`vera-ingest-docling`) uses a layout model that can emit
`PictureItem` regions from rendered pages, but its picture classifier and VLM
extras are explicitly not enabled, and it is untested on D-size sheets.

**Consequence:** "match each text hit to vera's already-extracted figure"
works for scanned sheets but **not** for the vector majority. The plansheet
pipeline must **synthesize detail figures**: segment each detail region, render
it to PNG, and emit it as an `image` block so it becomes a normal figure
attachment. Then the existing figure surface (`vera figures`, `--figures`,
`vera_figures`, `vera_get_figure`, `figures_for`) works unchanged. P0 below
measures this on real ISE sheets before committing.

### 2.3 Metadata filtering is exact-match on top-level scalar keys

`vera_doc._where.metadata_matches`: distinct keys are AND, a list *filter*
value is IN, scalar equality otherwise, and **list-valued stored metadata is not
matched as IN**. There is no range operator. Convert `--metadata KEY=VALUE`
stamps every chunk. Indexed directory search (`.vera-index/`) matches convert
`--metadata` tags and convert-owned headers. Other chunk-metadata keys hit
`CHUNK_METADATA_FILTER_REASON` ("chunk metadata filter not in collection
index") and take the safe fallback path.

**Consequences for the schema (section 4):**

- Set-level facets that should filter everywhere (jurisdiction, development
  type, phase, acreage bucket) are stamped as **scalar top-level keys on every
  chunk** of the archive, the same way `--metadata` does.
- Multi-valued facts (features present, detail types present) get **one chunk
  per item** with a scalar key (`cd_detail_type: "flume"`), not a list.
- Acreage ranges need either a precomputed bucket (`cd_acreage_bucket: "1-5"`)
  for P1 or a new range operator. P4 adds `gte` and `lte` to `where`, and to the
  collection index.

### 2.4 Storage and mutation

- VERA 0.2 has no figures, pages, or blocks tables. Viewer data lives in
  attachments (`viewer_pages`, `viewer_blocks`, `source_original`) with
  pointers in `archive_metadata`.
- `VeraDocument` supports transactional `upsert`, `put_attachments`,
  `write_attachment`, `delete_attachment`, and `set_metadata`. An enrichment
  pass can therefore update an existing archive in place without reconverting.
- Convert skips re-conversion only when `source_file_hash` matches, so
  `source_file_hash` is the natural cache key.

### 2.5 Search and MCP surface

- Search modes: `keyword` (FTS5 bm25), `semantic` (cosine), `hybrid`
  (min-max normalized, equal weight). No reranker exists today.
- MCP (`vera_mcp/server.py`) exposes 11 tools: `vera_library_info`,
  `vera_search`, `vera_corpus_search`, `vera_library_status`, `vera_inspect`,
  `vera_validate`, `vera_figures`, `vera_get_figure`, `vera_get_page`,
  `vera_get_chunk`, `vera_get_chunk_regions`. Policy clamps
  (`access_policy.py`) apply to `top_k` and context.
- `vera eval` measures hit rate and MRR on one archive from a JSON query set.
  `vera-lab` renders block and chunk overlays to HTML for one PDF.

### 2.6 Repo rules this design must respect

- Dependencies point inward. `vera-doc` must not learn about plan sets.
- ROADMAP non-goals: name plugin packages after the engine or approach, not the
  file type. Do not bundle large ML runtimes in the base install without an
  explicit opt-in. Never silently fall back to a different pipeline.

---

## 3. Architecture overview

```text
            convert time (fast, CPU, deterministic)                 background (slow, optional, GPU/CPU)
 PDF ──> vera-ingest-plansheet pipeline ──> .vera archive ──> vera enrich (plansheet enricher) ──> same .vera (upserted)
         • reuse pymupdf text + OCR                          • VLM OCR for garbled/scanned pages
         • sheet index + title block parse                   • VLM sheet classification fallback
         • sheet classification (rules)                      • site-feature list on plan sheets
         • detail segmentation (vector geometry)             • detail type + purpose
         • detail figures as image blocks                    • VLM bboxes for scanned sheets (snapped)
         • callout graph                                     • set rollup gaps
         • set rollup from folder path + cover sheet         • cache keyed by source_file_hash + page
                                                     │
                                                     ▼
                         search: keyword/semantic → (text rerank) → figures → (vision rerank) → results
```

Package layout (new):

```text
packages/vera-ingest-plansheet/
  pyproject.toml                      # entry points below; extras: [vlm]
  src/vera_ingest_plansheet/
    __init__.py                       # create_pipeline, create_descriptor, create_enricher
    options.py                        # PlansheetOptions(PipelineOptions)
    pipeline.py                       # plansheet_pipeline(source_path, request) -> IngestResult
    titleblock.py                     # sheet number/title, sheet index parse
    classify.py                       # rule-based sheet classification
    segment.py                        # detail segmentation from vector geometry
    callouts.py                       # "SEE DETAIL 4/C-7" parser + graph
    rollup.py                         # folder path + cover sheet → set profile
    vocab.py                          # controlled vocabularies (enums) + synonyms
    schema.py                         # pydantic/dataclass models + JSON Schema export
    enrich/
      __init__.py                     # enrich(archive_path, options) entry
      backends.py                     # VLMBackend protocol: ollama, llamacpp, vllm, openai-compatible
      prompts.py                      # versioned prompts
      cache.py                        # sqlite cache keyed by (source_file_hash, page, task, prompt_version, model)
      tasks.py                        # ocr, classify, features, details, bbox
    search.py                         # search_details / find_figures helpers
  tests/
```

Naming: the ROADMAP says "engine, not file type". The input is still PDF. The
package is named for the approach, *plan-sheet* layout analysis, and the
provider name is `plansheet`. It advertises `.pdf` in
`PipelineCapabilities.source_formats`, and users select it with
`--parser plansheet`. It never replaces `pymupdf` silently.

Entry points:

```toml
[project.entry-points."vera.ingest_pipelines"]
plansheet = "vera_ingest_plansheet:create_pipeline"

[project.entry-points."vera.ingest_pipeline_descriptors"]
plansheet = "vera_ingest_plansheet:create_descriptor"

# NEW group, proposed by this design (does not exist yet)
[project.entry-points."vera.enrichers"]
plansheet = "vera_ingest_plansheet:create_enricher"
```

---

## 4. Data model

All new chunk metadata keys use the `cd_` prefix (construction documents) to
avoid collisions. Every structured item carries a locator:

```json
{"page_number": 37, "bbox": [x0, y0, x1, y1], "page_width": 3024.0, "page_height": 2160.0}
```

These are page points with a top-left origin, the same contract as
[`regions`](../figures-and-regions.md#coordinate-conversion).

### 4.1 Controlled vocabularies (`vocab.py`)

Each enum has `other`, and when `other` is used a short free `*_label` is
required. Nothing is lost, and the vocabulary grows by reviewing `other`
labels (`vera enrich --report-other`). Each enum value carries a synonym list
used by rules, search-time query expansion, and prompts.

**`SheetType`**: `cover`, `index`, `general_notes`, `existing_conditions`,
`survey`, `demolition`, `site_layout`, `grading`, `drainage`, `utility`,
`sanitary_sewer`, `water`, `storm_profile`, `road_profile`, `erosion_control`
(ESPC/SWPPP), `landscape`, `tree_protection`, `lighting`, `signage_striping`,
`traffic_control`, `structural`, `details`, `cross_sections`, `hydrology`,
`other`.

**`FeatureType`** (plan sheets): `building`, `parking_lot`, `drive_aisle`,
`roadway`, `sidewalk`, `curb_gutter`, `retaining_wall`, `detention_pond`,
`retention_pond`, `underground_detention`, `water_quality_bmp`,
`bioretention`, `septic_field`, `sanitary_sewer`, `force_main`,
`lift_station`, `water_main`, `fire_hydrant`, `storm_pipe`, `inlet`,
`headwall`, `flume`, `riprap`, `swale_ditch`, `culvert`, `stream_buffer`,
`wetland`, `floodplain`, `dumpster_pad`, `fence`, `other`.

**`DetailType`** (detail sheets): `flume`, `headwall`, `endwall`,
`inlet_catch_basin`, `junction_box`, `manhole`, `outlet_control_structure`,
`riprap_apron`, `level_spreader`, `curb_gutter`, `curb_cut`, `valley_gutter`,
`pavement_section`, `sidewalk`, `ada_ramp`, `retaining_wall`, `pipe_bedding`,
`trench`, `cleanout`, `thrust_block`, `hydrant_assembly`, `valve`,
`backflow`, `septic_component`, `construction_exit`, `silt_fence`,
`inlet_protection`, `check_dam`, `sediment_basin`, `skimmer`, `fence_gate`,
`bollard`, `dumpster_enclosure`, `sign_striping`, `planting`, `other`.

Example synonyms: `flume` covers flume, concrete flume, paved rundown, curb cut
channel, and spillway chute. `riprap_apron` covers rip rap apron, outlet
protection, and stone apron.

**`DevelopmentType`**: `commercial`, `retail`, `office`, `industrial`,
`warehouse`, `residential_subdivision`, `multifamily`, `townhome`,
`institutional`, `school`, `church`, `park_recreation`, `roadway`, `utility`,
`stormwater_retrofit`, `mixed_use`, `other`.

**`Phase`**: `concept`, `permit`, `bid`, `ifc`, `conformed`, `asbuilt`,
`unknown`.

### 4.2 Purpose and provenance (applies to details and features)

```json
"purpose": {
  "text": "Concrete flume carrying parking lot runoff through a curb opening into the detention pond.",
  "basis": "observed",          // observed = stated in title/notes/callout; inferred = model interpretation
  "evidence": [ {"page_number": 12, "bbox": [...], "quote": "FLUME AT CURB CUT TO POND"} ],
  "confidence": 0.82,
  "source": "rule|vlm",
  "model": "qwen3-vl-8b-instruct-q4_k_m",
  "prompt_version": "details.v1"
}
```

Rule: `basis = "observed"` requires at least one `evidence` quote found in the
page text layer. Otherwise the validator rewrites it to `inferred`.

### 4.3 Records and how they map to VERA 0.2

| Logical record | Stored as | Key metadata |
|---|---|---|
| **SetProfile** (one per PDF) | `archive_metadata["cd_set"]` JSON + attachment `cd_set_profile` (JSON) + scalar facets stamped on **every chunk** | `cd_project_number`, `cd_client`, `cd_jurisdiction_county`, `cd_jurisdiction_city`, `cd_agency`, `cd_dev_type`, `cd_phase`, `cd_date`, `cd_acreage_total`, `cd_acreage_disturbed`, `cd_acreage_bucket`, `cd_lots`, `cd_building_sf` |
| **Sheet** (one per page) | attachment `cd_sheets` (JSON array) + per-page "sheet header" chunk | `cd_record: "sheet"`, `cd_sheet_number` (e.g. `C-501`), `cd_sheet_title`, `cd_sheet_type`, `cd_sheet_type_source` (`titleblock\|index\|rule\|vlm`), `cd_sheet_type_confidence` |
| **Detail** (one per detail) | `image` block → figure attachment (rendered PNG crop) + one chunk whose `block_ids` include the image block and the title/notes blocks | `cd_record: "detail"`, `cd_detail_number` (e.g. `4`), `cd_sheet_number`, `cd_detail_title`, `cd_detail_type`, `cd_detail_type_label`, `cd_purpose` (object, 4.2), `cd_segmentation` (`vector\|existing_figure\|vlm\|tile`), `cd_segmentation_confidence`, `regions` |
| **Feature** (one per feature per plan sheet) | chunk | `cd_record: "feature"`, `cd_feature_type`, `cd_feature_label`, `cd_purpose`, `regions` (bbox when known) |
| **Callout** (edge) | attachment `cd_callouts` (JSON array) + `cd_callouts_from` on detail chunks | `{from: {page, bbox, text}, to: {sheet_number, detail_number}, resolved_detail_chunk_id}` |
| **Rollup lists** | `cd_set_profile` JSON (`features_present`, `detail_types_present`, counts) | not used for filtering; filter via per-item chunks |

Detail chunk `text` is built for keyword search and stays human-readable:

```text
DETAIL 4 / C-501 — CONCRETE FLUME
Type: flume. Purpose (observed): flume at curb cut to pond.
Notes: 4" 3000 PSI CONCRETE ... #4 BARS @ 12" O.C. ...
Called out from: C-300 Grading Plan (2 callouts).
```

`embedding_text` adds synonyms and set context (jurisdiction, development
type) so semantic queries like "paved channel at curb opening" land.

### 4.4 Model output schema

`schema.py` defines dataclasses or pydantic models for each VLM task and
exports a JSON Schema. Backends must use constrained or JSON-mode decoding
where available (Ollama `format`, vLLM `guided_json`, llama.cpp grammar).
Every response is validated. On failure, retry once with the validation error
appended, then record the page under `diagnostics["cd_enrich_failures"]`.
Never write unvalidated output.

---

## 5. Pipeline stages

### 5.1 Text (convert time, plus enrichment fallback)

1. Reuse `vera_ingest_pymupdf.parser.parse_pdf_structured` for text blocks,
   tables, and selective Tesseract OCR. Do not fork it. If a hook is needed,
   add a small public function to `vera-ingest-pymupdf`, such as returning raw
   PyMuPDF `page` objects or drawings, in a separate PR.
2. Per page, compute a **text quality score**: native char count vs sheet
   area, fraction of dictionary words, fraction of replacement or garbage
   glyphs, SHX-font artifacts (CAD text exported as vector strokes produces no
   text at all). Pages below the threshold are flagged
   `cd_text_quality: "low"` for the enricher.
3. Enrichment: VLM OCR only on `low` pages, in high-res tiles (5.6). Results
   are upserted as additional chunks with `cd_text_source: "vlm_ocr"`.

### 5.2 Sheet identification and classification (convert time, rules first)

1. **Title block**: search the lower-right and right-edge strip for a
   sheet-number pattern (`^[A-Z]{1,3}[-.]?\d{1,3}(\.\d+)?$`, e.g. `C-501`,
   `C5.01`, `ESC-2`), plus the largest-font title nearby.
2. **Sheet index**: on cover or index sheets, parse the "SHEET INDEX" table
   (pdfplumber table or text columns) into `{sheet_number: title}`, and use it
   to confirm or fill per-page values.
3. **Rules**: map title keywords and discipline prefixes to `SheetType`
   (synonyms in `vocab.py`), e.g. `DETAIL` → `details`; `EROSION`, `ESPC`,
   `SWPPP`, `ES&PC` → `erosion_control`.
4. If confidence stays below the threshold, mark the page for
   **VLM classification** in enrichment (a full-sheet thumbnail plus a
   title-block crop).

### 5.3 Per-set rollup (convert time, enrichment fills gaps)

Sources, in priority order, recorded per field as `source`:

1. **Folder path.** This is the strongest source. Parse the relative path
   under the library root, for example
   `Construction Plans\<Client>\1093.1301 - Riverside Commons\...\Plans_IFC.pdf`:
   project number `^\d{3,4}\.\d{3,4}`, project name, client folder, and phase
   keywords in the file or folder name (`IFC`, `Bid`, `Permit`, `Conformed`,
   `As-built`, `Rev N`). Make the path patterns configurable
   (`--pipeline-option path_patterns=...`) since every firm differs.
2. **Cover sheet text**: jurisdiction (`<NAME> COUNTY`, `CITY OF <NAME>`,
   permitting agency), address, date, owner or developer, and the **site data
   table** (total acreage, disturbed acreage, lots, building SF, zoning).
3. **VLM** on the cover sheet and site data table only when fields are missing.

Normalize jurisdictions against a small gazetteer file (county and city names
per state, extensible), and compute `cd_acreage_bucket`
(`<1`, `1-5`, `5-10`, `10-25`, `25-50`, `50+`).

### 5.4 Enrichment hook (new extension point)

Nothing post-ingest exists today. Proposal:

- New entry-point group `vera.enrichers`. An enricher is
  `Callable[[VeraDocument, EnrichRequest], EnrichResult]`, mirroring the
  pipeline contract. `EnrichRequest` carries `enricher_options`, `cancel`, and
  a progress callback. `EnrichResult` reports counts, diagnostics, and
  warnings.
- New CLI: `vera enrich FILE_OR_DIR --enricher plansheet [--recursive]
  [--enricher-option KEY=VALUE] [--only TASKS] [--dry-run] [--json]`.
  It opens each archive read-write, runs inside `VeraDocument.transaction()`,
  upserts chunks and attachments, and records
  `archive_metadata["enrichment"]["plansheet"] = {version, model,
  prompt_versions, completed_pages, source_file_hash, finished_at}`.
- Put the generic registry in `vera-ingest` (next to the pipeline registry),
  not in `vera-doc`.
- **Resumable**: progress is per page. A crash resumes from
  `completed_pages`.
- **Incremental**: skip archives whose `enrichment.plansheet.source_file_hash`
  equals `source_file_hash` and whose model and prompt versions are
  unchanged.
- **Survives reconversion**: results are also cached outside the archive in
  `~/.cache/vera/enrich/plansheet.sqlite`, keyed by
  `(source_file_hash, page_number, task, prompt_version, model)`, so
  reconverting a file re-applies enrichment without new GPU work.
- Embeddings for new chunks use the archive's `default_embedding_model`. The
  enricher must refuse to run if that embedder is unavailable, with no silent
  fallback.
- After enrichment, `vera index update` refreshes `.vera-index/`.

### 5.5 Site features (enrichment, plan sheets only)

For sheets typed `site_layout`, `grading`, `drainage`, `utility`,
`erosion_control`, and similar:

1. **Rule pass at convert time.** Match legend and label text against
   `FeatureType` synonyms (`SEPTIC`, `DRAIN FIELD`, `RET. WALL`, `POND`,
   `FH`, `SSMH`, ...). Each hit gives a feature with the label's bbox and
   `basis: observed`.
2. **VLM pass.** Send the sheet (tiled) plus the rule hits, and ask for the
   features present with approximate bboxes and short purpose text.
   Deduplicate against the rule hits by type and IoU.
3. Roll up into `features_present` with counts.

### 5.6 Details: segmentation, linking, callouts

**Detail sheet segmentation** (convert time, vector first):

1. **Find titles.** Detail title blocks are text such as `4` (a bubble
   number) next to `CONCRETE FLUME` and `SCALE: NTS` or `N.T.S.`. Use
   regexes plus font size, bold weight, and underline drawings from
   `page.get_drawings()`.
2. **Find frames.** From `page.get_drawings()`, collect long horizontal and
   vertical segments and rectangles. Many firms frame each detail in a grid
   cell. Build candidate cells from the line grid.
3. **Assign.** Each title selects the cell that contains it. Titles usually
   sit just **below** the detail, sometimes above. With no frame, grow a
   region from the title upward (or downward) until whitespace gaps, the next
   title's region, or the sheet border or title block.
4. **Validate.** Check that the number of regions equals the number of titles
   found, that regions do not overlap beyond a tolerance, and that each region
   holds a minimum fraction of vector ink. On failure, mark the page
   `cd_segmentation: "needs_vlm"`.
5. **Noisy geometry guard.** Flattened PDFs can have more than 50,000 tiny
   path segments. Cap drawing count per page and fall back to the
   rendered-raster path.
6. **Emit figures.** Render each region with `page.get_pixmap(clip=rect,
   dpi=200)` as a PNG `IngestBlock(block_type="image", bbox=rect,
   image_bytes=...)`. Emit the title as `block_type="caption"` so the
   existing `_caption_for_figure` logic finds it. Put both block IDs in the
   detail chunk's `block_ids` so the figure links to the chunk.
   Reuse `_drop_repeated_images`-style hashing, but on rendered content plus
   page, since identical standard details across sets should still be kept
   per set.

**Reuse existing figures when present.** If a page already has raster image
blocks, which is typical for scanned sheets, test each title against them.
When a figure contains the title or sits nearest it (title just below or
above the figure, within `_CAPTION_PROXIMITY`-like distance), and the figure
covers about one detail (area check), link it with
`cd_segmentation: "existing_figure"`. A whole-sheet figure is never treated
as one detail. It goes to the VLM path.

**VLM bbox fallback** (enrichment; scanned or `needs_vlm` pages):

1. Render at high resolution and cut into overlapping tiles (for example
   1536 px tiles, 20% overlap). D-size sheets downscaled to one image lose
   small details.
2. Ask Qwen3-VL for `[{detail_number, title, bbox}]` per tile. Map the
   coordinates back to page points and merge across tiles (NMS by IoU, same
   title).
3. **Snap** each box to the nearest vector frame lines or whitespace gaps
   when vector data exists. VLM boxes are usually close but loose.
4. **Cross-check** the count against the OCR or text titles, and flag any
   mismatch in diagnostics.

**Callout following** (convert time):

- Parse callouts on all sheets: `SEE DETAIL 4/C-7`, `DETAIL 4 SHEET C-7`,
  `4/C-501`, and bubble pairs (a number above a sheet number in a circle,
  detected from text proximity inside a circle drawing).
- Resolve to `(sheet_number, detail_number)` through the sheet map from 5.2.
  Link to the detail chunk.
- Store reverse edges so each detail knows the plan sheets and locations that
  reference it. These give the **purpose context** passed to the VLM in 5.7,
  such as a callout on the parking lot edge next to the pond.
- A search hit on a callout resolves to the actual detail figure.

### 5.7 Detail type and purpose (convert time rules, enrichment VLM)

1. **Rules.** Map the title against `DetailType` synonyms. An exact synonym
   match gives a confident type with `source: rule`.
2. **VLM.** Input: the detail crop, its title and notes text, the sheet title
   and type, the set development type, and **up to 3 callout-context crops**
   from referencing plan sheets. Output: `detail_type`, `detail_type_label`,
   and `purpose` per 4.2.
3. The validator enforces the enum, the `other` label, and the
   observed/inferred evidence rule.

---

## 6. Search flow

```text
query ("flume", optional filters)
  1. expand query with vocab synonyms (flume → rundown, spillway chute, curb cut channel)
  2. hybrid search over chunks, where={cd_record: "detail", cd_jurisdiction_county: ..., ...}
     plus callout and plan-sheet chunks (callouts resolve to details)
  3. optional text reranker when hits > N (default 50): cross-encoder on chunk text, keep top 20–50
  4. map hits → detail figures (block_ids / cd_callouts); dedupe per detail
  5. optional vision reranker: VLM scores (figure image, query) → 0–1, keep top K
  6. results: thumbnail, detail title, type, purpose, project, sheet number/title, page, bbox, file
```

- The **text reranker** is optional and pluggable (for example a local
  `bge-reranker` cross-encoder through the `ml` extra). It only judges text.
- The **vision reranker** is where "is this actually a flume detail" gets
  decided. It runs on a handful of crops per query, so it is cheap even
  locally. Cache scores by `(asset hash, normalized query, model)`.
- Both rerankers default **off** in CLI and MCP and are enabled per call.
  Desktop Chat may enable them when a VLM backend is configured.

### 6.1 Proposed API and tools

Python (`vera_ingest_plansheet.search`):

```python
search_details(
    target,                      # VeraDocument | VeraCorpus | path
    query: str,
    *,
    detail_type: str | list[str] | None = None,
    feature: str | list[str] | None = None,     # set has this feature
    jurisdiction: str | None = None,             # county or city, normalized
    dev_type: str | list[str] | None = None,
    phase: str | list[str] | None = None,
    acreage_min: float | None = None,
    acreage_max: float | None = None,
    top_k: int = 10,
    text_rerank: bool = False,
    vision_rerank: bool = False,
) -> list[DetailHit]   # each with figure asset_id, regions, citation fields, set profile subset

search_sets(... same facets ..., query: str | None = None) -> list[SetHit]
```

CLI: `vera details search PATH "flume" --jurisdiction Gwinnett --dev-type
commercial --acreage-max 5 --vision-rerank --json` and `vera details sets
PATH --feature septic_field --json`. Both support `--out-dir` to write
thumbnails, like `vera figures`.

MCP (adds 2 to the current 11, same access policy and clamps):

- `vera_search_details(query, file|library, filters..., top_k, vision_rerank)`
  returns metadata, with images fetched through the existing `vera_get_figure`.
- `vera_search_sets(filters..., query)` returns set profiles with file paths.

Viewer and desktop (P4): a Details view with a thumbnail grid, facet filters,
and click-through to the sheet with the bbox highlighted. Reuse
`regions` rendering. A set-catalog table and map are optional, using the
address or coordinates from the rollup.

---

## 7. Models and backends

### 7.1 Default model

- **Qwen3-VL-8B-Instruct.** This is the starting point. It reads text in
  images well and natively outputs bounding boxes. Hardware: full precision
  needs a 16–24 GB GPU (RTX 4080/4090 class). Quantized (Q4/Q5 GGUF or AWQ),
  it fits in about 8–12 GB (RTX 4070 class).
- **Qwen3-VL-2B / 4B** are for weak hardware or CPU and Mac. They are slower
  and less accurate. Use them for classification only.
- **GLM-4.6V** led open models on AECV-Bench but is too heavy for most
  offices. Support it only through a hosted or vLLM backend.
- **MechVL-4B** (a Qwen3-VL fine-tune on mechanical drawings) shows that
  domain fine-tuning of a small model pays off. A future option is to
  fine-tune on ISE labels (section 9).
- **AECV-Bench** (2026, arXiv 2601.04819) found VLMs good at OCR and text
  reading, weaker at spatial reasoning, and weakest at symbol interpretation.
  Design implication: lean on text plus layout rules for structure, and use
  the VLM for reading, recognition, and purpose. Do not trust VLM counts or
  dimensions without cross-checks.

### 7.2 Pluggable backend (`enrich/backends.py`)

```python
class VLMBackend(Protocol):
    name: str
    model: str
    def generate(self, images: list[bytes], prompt: str, *, json_schema: dict | None,
                 max_tokens: int, temperature: float = 0.0) -> str: ...
```

Implementations:

- `ollama`, the easiest local option (HTTP `localhost:11434`, `format` = JSON
  Schema).
- `llamacpp` (llama-server, OpenAI-compatible, grammar or JSON Schema).
- `vllm`, for batch throughput (OpenAI-compatible, `guided_json`).
- `openai_compatible`, for any hosted endpoint, **opt-in only**. The CLI and
  desktop must show that pages will leave the machine.

The base install pulls in no torch or transformers. Backends talk HTTP
through the `[vlm]` extra, which needs only `httpx`. Configure with
`--enricher-option backend=ollama model=qwen3-vl:8b endpoint=...`. If the
backend is unreachable, fail clearly. Never skip silently.

---

## 8. Cost and performance

- Scale: 502 sets, about 15k–30k sheets, of which roughly 10–20% are detail
  sheets (about 3k–5k sheets, 20k–40k details).
- Convert-time cost is CPU only and should stay within about 2× of today's
  `pymupdf` convert time per sheet (acceptance criterion in P1). `get_drawings`
  on dense sheets is the main risk, so cap it (5.6).
- Enrichment skips work wherever possible: text-quality-good pages skip VLM
  OCR; rule-confident sheets skip VLM classification; rule-typed details still
  get VLM purpose (configurable). These estimates are rough, not benchmarks:
  an 8B quantized model at about 2–6 s per call on a mid-range GPU means a
  full corpus pass is a day or two in the background. Pilot timing in P0 or P3
  replaces these numbers.
- The enrichment job is a background, resumable, incremental, throttleable
  process (`--max-pages-per-run`, `--gpu-concurrency`), cached by
  `source_file_hash` (5.4).

---

## 9. Evaluation

Build a labeled ISE test set under `dev/benchmarks/plansheet/` with labels
only, no client PDFs committed. PDFs are referenced by path in a local config.

- **~20 sets** covering vector and scanned sheets, at least 4 jurisdictions,
  at least 4 development types, and 2+ title-block styles. Labels: sheet
  number, title, and `SheetType` per page, plus SetProfile fields.
- **~50 detail crops** (and their sheets). Labels: per-detail bbox, title,
  `DetailType`, and purpose basis.
- **Retrieval queries** (about 20): `flume`, `riprap apron`, `headwall`,
  `construction exit`, `septic`, `retaining wall`, `underground detention`,
  plus faceted ones. Express them as `vera eval`-compatible JSON where
  possible (`expected_pages`/`expected_terms`). Add a `plansheet eval` script
  for detail-level relevance (expected `(file, sheet_number, detail_number)`).

Metrics and initial targets (adjust after P0):

| Metric | Target |
|---|---|
| Sheet number extraction accuracy | ≥ 95% |
| Sheet type accuracy (rules + VLM) | ≥ 90% |
| SetProfile field accuracy (jurisdiction, phase, dev type, acreage) | ≥ 90% each, when present on sheets |
| Detail segmentation: one region per detail, IoU ≥ 0.7 | ≥ 85% vector, ≥ 70% scanned |
| Detail count match vs titles | ≥ 95% of detail sheets |
| Detail type precision / recall | ≥ 0.90 / ≥ 0.85 |
| Callout resolution rate (resolvable callouts) | ≥ 90% |
| "flume" and similar queries: recall@20 (details) | ≥ 0.9; nDCG@10 improves with vision rerank |
| Observed-purpose evidence validity | 100% (validator-enforced) |

`vera-lab` should gain a `--parser plansheet` overlay showing detail regions,
titles, and callout edges for visual QA.

**Pilot gate:** run the full pipeline on the 20 sets and review the metrics
before processing all 502.

---

## 10. Phased plan

Each phase is a separate PR (or a small stack) with tests. Unit tests use
synthetic PDFs generated in tests with PyMuPDF (vector frames, titles,
callouts). No client data goes in the repo.

### P0: Spike: measure what exists (1–2 days)

- Script `dev/benchmarks/plansheet/probe.py`: for N sample sets, convert with
  `pymupdf` (and `docling` if installed). Report per page: native char count,
  image block count and coverage, `get_drawings()` count, and whether any
  figure is about one detail in size.
- **Accept:** a short report (`dev/benchmarks/plansheet/P0.md`) confirming or
  refuting section 2.2 on ISE sheets, drawing-count distribution,
  scanned-page share, and one or two example sets per title-block style.

### P1: Plansheet pipeline, sheet classification, and set rollup (no VLM)

- New package `vera-ingest-plansheet` with entry points, `PlansheetOptions`,
  and descriptor. It reuses `parse_pdf_structured`.
- Modules `titleblock.py`, `classify.py`, `rollup.py`, `vocab.py`, and
  `schema.py`. Sheet-header chunks, `cd_sheets` attachment, `cd_set`
  metadata, and scalar facets on every chunk.
- Text-quality scoring and `cd_text_quality`.
- Docs: `docs/packages/vera-ingest-plansheet.md` and a nav entry.
- **Accept:** `vera convert set.pdf --parser plansheet` produces a valid
  archive (`vera validate` passes). `vera search ./plans "x" --where
  cd_jurisdiction_county=Gwinnett --where cd_dev_type=commercial` works.
  Sheet number ≥ 95% and sheet type (rules only) ≥ 80% on the 20-set test
  set. Convert time ≤ 2× `pymupdf`. Selecting `pymupdf` behaves exactly as
  before.

### P2: Detail segmentation, figure linking, and callouts (no VLM)

- `segment.py` (vector frames, title anchoring, grow-to-whitespace, noisy
  geometry guard), rendered detail figures as image blocks plus caption
  blocks, existing-figure reuse, and `callouts.py` with the reverse edge
  graph.
- Rule-based `DetailType` from titles.
- `vera-lab` overlay for detail regions and callouts.
- **Accept:** on vector sheets, segmentation ≥ 85% at IoU ≥ 0.7 and count
  match ≥ 95%. `vera figures set.vera` lists one figure per detail with the
  title as its caption. `vera search set.vera "flume" --figures --json`
  returns the detail figure. Callout resolution ≥ 90%.

### P3: Enrichment hook, VLM backends, and enrichment tasks

- `vera.enrichers` registry in `vera-ingest`, the `vera enrich` CLI,
  `EnrichRequest`/`EnrichResult`, progress, resumability, cache, and
  `archive_metadata["enrichment"]`.
- Backends: ollama, llamacpp, vllm, openai_compatible (opt-in). JSON Schema
  validation with retry.
- Tasks: VLM OCR (low-quality pages), sheet classification fallback, VLM bbox
  for scanned or `needs_vlm` pages (tiling, merge, snap, cross-check),
  features, detail type and purpose (with callout context), and rollup gap
  fill.
- **Accept:** `vera enrich ./plans --enricher plansheet --enricher-option
  backend=ollama --enricher-option model=qwen3-vl:8b --recursive` completes on
  the 20-set pilot. Killing and restarting resumes. Re-running is a no-op.
  Reconverting plus re-enriching uses the cache with zero model calls. Metric
  targets in section 9 are met or the gaps are documented. Throughput is
  reported.

### P4: Search tools, filters, rerankers, and UI

- `search_details` and `search_sets`, the `vera details` CLI, and MCP
  `vera_search_details` and `vera_search_sets` with access-policy clamps.
- Query synonym expansion, optional text reranker, and vision reranker with
  score cache.
- `where` range operators (`{"cd_acreage_total": {"gte": 1, "lte": 5}}`) in
  `vera_doc._where` and the collection index, plus promoting `cd_*` facet
  keys into `.vera-index/` so indexed search does not take the fallback path.
  Coordinate with the format and index docs; no `format_version` change.
- Desktop Details view: thumbnail grid, facets, and click-through highlight.
- **Accept:** "Gwinnett commercial sites under 5 acres with underground
  detention" and "flume details" return correct, cited results on the pilot
  corpus. Recall and nDCG targets are met. MCP tool tests are added. Docs are
  updated (`mcp.md`, `searching.md`, `cli-reference.md`).

### P5 (later): Full corpus and refresh

- Run on all 502 sets, schedule an incremental refresh with the ISE_Assets
  rebuild, and run the `other`-label review loop that grows the vocabularies.

---

## 11. Out of scope

- Quantity takeoffs, dimension extraction, or checking calculations from
  drawings.
- CAD-native ingest (DWG/DXF) and BIM. PDF only.
- Plan review and compliance checking against GSMM or local manuals (a
  possible later feature that builds on this data).
- Fine-tuning a model (data collection is designed for it, but training is
  not in scope).
- Changing the VERA file format or `vera-doc` dependencies.
- Hosted or cloud processing as a default.

## 12. Open questions

1. **Segmentation reality.** P0 decides how much of section 2.2 holds on ISE
   sheets, and whether Docling's layout `PictureItem` regions on rendered
   sheets are worth using as an extra signal.
2. **One archive per set vs per sheet.** The design assumes one `.vera` per
   PDF set. Some sets are split across several PDFs (per discipline). Should
   the rollup merge them by project number and phase?
3. **Duplicate sets.** The same project often has Permit, IFC, and Conformed
   sets. Should default search collapse to the latest phase per project?
4. **Standard details.** Firm-standard details repeat across hundreds of
   sets. Should they be deduplicated by perceptual hash and shown as "used in
   N projects"?
5. **Where enrichment results live.** In-archive upsert (proposed) vs a
   sidecar `.vera` per set. In-archive keeps a single file but mutates
   artifacts that convert produced.
6. **Range filters.** Is P1's bucket field enough, or should range operators
   move earlier than P4?
7. **Desktop packaging.** The VLM backend is external (Ollama). Does the
   desktop app detect Ollama and offer setup, or stay CLI-first for this
   feature?
8. **Jurisdiction gazetteer.** Bundle Georgia, Arkansas, and North Carolina
   first (ISE's footprint), or require a firm-supplied list?
9. **Vocabulary governance.** Who approves promoting an `other` label into an
   enum value, and does that trigger re-enrichment?

## 13. References

- [Creating an ingest pipeline plugin](../creating-an-ingest-pipeline.md)
- [Figures and highlight regions](../figures-and-regions.md)
- [Format specification 0.2](../vera-spec-v0.2.md)
- [Search](../searching.md), [Evaluation](../evaluation.md), [MCP](../mcp.md), [Architecture](../architecture.md)
- AECV-Bench: <https://www.arxiv.org/pdf/2601.04819>
- Qwen3-VL models: <https://huggingface.co/Qwen>
- MechVL-4B: <https://huggingface.co/posts/XiaofengAlg/349825134235451>
