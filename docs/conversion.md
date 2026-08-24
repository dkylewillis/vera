# Convert documents

`vera convert` turns PDFs into portable `.vera` archives. Conversion parses
page layout, detects headings and figures, creates citation-ready chunks,
computes embeddings, builds the FTS5 keyword index, and normally stores the
original PDF. Batch discovery and the desktop source viewer are PDF-only in
this release. Planned DOCX/HTML/Markdown ingest and a stored-Markdown
preview for visual grounding are in
[Additional source formats and visual grounding](multi-format-ingest.md).

## Convert one PDF

```bash
vera convert "input.pdf" "output.vera"
```

Omit the output to create a same-named archive:

```bash
vera convert "input.pdf"
```

Single-file conversion builds and validates a temporary sibling archive before
atomically replacing the output path. If parsing, writing, or validation
fails, VERA removes the temporary file and preserves any existing output.

Conversion uses selective OCR by default. Native-text pages keep the fast
PyMuPDF extraction path; image-dominant pages with little or no text are
recognized locally with Tesseract. A PDF that still produces no chunks fails
with a message that it may be scanned and requires OCR.

## OCR

Automatic OCR is the default for pipelines that advertise OCR fields:

```bash
vera convert "scan.pdf" "scan.vera" --ocr auto
```

With the default PyMuPDF pipeline (`vera-ingest-pymupdf`), OCR runs only on
pages that are mostly a scanned image and have too little native text to
search reliably. A large-image page with fewer than 200 alphanumeric
characters is treated as sparse native text (headers, Bates stamps, or
letterhead) and is still OCR'd. Genuinely blank pages and native-text pages
without a large image skip OCR. Mixed PDFs can therefore use native
extraction on ordinary pages and OCR on scanned pages in one conversion.

Legacy CLI aliases (forwarded only when the selected pipeline advertises the
matching descriptor field):

- `--ocr auto` selects scanned pages (default);
- `--ocr off` never invokes OCR;
- `--ocr force` OCRs every page, replacing native text extraction;
- `--ocr-language eng` selects language data (PyMuPDF/Tesseract default);
- `--ocr-dpi 300` controls recognition resolution (PyMuPDF only).

Prefer provider-owned options when you need an explicit override:

```bash
vera convert "scan.pdf" "scan.vera" \
  --pipeline-option ocr_mode=force \
  --pipeline-option ocr_language=eng \
  --pipeline-option ocr_dpi=300
```

Explicit `--pipeline-option KEY=VALUE` values win over the legacy aliases for
the same key. See [Pipeline options](#pipeline-options).

VERA's `vera-ingest-pymupdf` package bundles the official `tessdata_fast`
English model and passes it directly to PyMuPDF's Tesseract integration.
Default English OCR therefore works offline without installing Tesseract or
configuring the system. Other
selected languages either require `--ocr-allow-download` (or the
`ocr_download` pipeline option) to fetch curated language data into a local
cache, or a manually installed `.traineddata` file with `TESSDATA_PREFIX`
set. Preview the registry and cache with `vera ocr-languages list` and fetch
packs ahead of time with `vera ocr-languages download fra`. Codes match
Tesseract's language list (for example `spa`, not `es`).
OCR failures name the page and language and preserve any existing destination.

OCR text is stored as ordinary paragraph blocks with page bounding boxes, so
search results and highlight regions work normally. This first OCR path targets
scanned prose. It does not reconstruct scanned tables, forms, or complex
multi-column reading order. For layout-aware parsing, install the optional
[`vera-ingest-docling`](packages/vera-ingest-docling.md) plugin and select
`--parser docling`.

## Convert a directory

Directory conversion writes each archive beside its PDF:

```bash
vera convert "./proposals"
```

Discover nested PDFs:

```bash
vera convert "./proposals" --recursive
```

Existing archives are validated before they are skipped. A sibling `.vera` is
skipped only when it validates and its stored `source_file_hash` matches the
current PDF. Changed PDFs and archives with a missing or unreadable hash are
reconverted. A malformed existing archive is reported separately and is not
silently preserved as a successful skip. Replace existing outputs explicitly:

```bash
vera convert "./proposals" --recursive --overwrite
```

Do not provide a single output path for directory conversion.

For a machine-readable batch report:

```bash
vera convert "./proposals" --recursive --json
```

The report distinguishes discovered, converted, same-source-hash skips,
malformed existing outputs, and conversion failures. `skipped_existing`
lists only unchanged valid archives. `malformed_existing` entries include
`input`, `output`, and validation `issues`. Batch conversion
continues after an individual PDF fails and exits nonzero if any conversion
failed or malformed existing output was found.

In the desktop app, right-click a folder in Explorer and choose
**Convert PDFs…** to open Convert in **PDF Directory** mode for that folder.
Confirm the ingest pipeline, embedding model, overwrite, and nested-folder
options, then convert.

## Reconvert with a different parser or embedding

Parser and embedding choices are stored in the archive at convert time.
Changing them means converting the PDF again and replacing the `.vera` file.

```bash
vera convert "./proposals" --recursive --overwrite --parser docling --model hashing
```

In the desktop app, right-click a `.vera` file in Explorer and choose
**Reconvert…**. Convert opens immediately with a preparing status while the
sibling PDF is resolved (or the embedded original is restored). Overwrite is
enabled, and the archive's current ingest pipeline, embedding model, and OCR
options are prefilled from inspect so you can change them before converting.
If inspect fails and no sibling PDF is listed, Reconvert does **not** export
an embedded original; Convert shows **Could not read archive metadata**. Place
the matching `.pdf` next to the archive, or open Document Info and export the
original once the archive is readable. After replacement, update the library
index if that folder is indexed.

## Embedding models

The default model is `hashing`:

```bash
vera convert "input.pdf" --model hashing
```

It is deterministic, local, and requires no machine-learning package. Equivalent
specs include `vera-hashing-384` and `hashing:vera-hashing-384`.

For neural embeddings, MiniLM uses ONNX Runtime (`vera-doc[onnx]`). Other
Sentence Transformers models still use the `ml` extra:

```bash
python -m pip install "vera-cli>=0.3.0" "vera-doc[onnx]>=0.3.0"
vera convert "input.pdf" --model sentence-transformers:all-MiniLM-L6-v2
```

The packaged Windows app already includes ONNX Runtime and vendors a
VERA-exported `all-MiniLM-L6-v2` graph in the installer (Convert label
**Local semantic (MiniLM)**), so that model does not download on first
desktop use. CLI MiniLM uses the `onnx` extra. Other model ids still use the
`ml` extra and may download from the Hub on first resolve.

Legacy slash-form names such as `sentence-transformers/all-MiniLM-L6-v2` and the
bare alias `all-MiniLM-L6-v2` still work.

The model name, vector dimension, and stored-vector normalization policy are
recorded in the archive. Both built-in embedders use L2 normalization. Search
uses the recorded model, so CLI machines that search a MiniLM archive still
need `vera-doc[onnx]` plus a MiniLM ONNX snapshot (`VERA_ONNX_MINILM_HOME`,
`app:dev`'s vendored graph, or the graph the Windows installer vendors).
When the `onnx` extra is installed, MiniLM does not fall back to Sentence Transformers.
Install `vera-doc[ml]` without the `onnx` extra if you want
MiniLM via Sentence Transformers from the Hub. The packaged desktop sidecar
already includes ONNX Runtime and the pinned graph.

Prefer `provider:model-id` specs. An unrecognized provider or model raises an
error at convert time instead of silently falling back to hashing. Third-party
plugins can register providers under the Python entry-point group
`vera.embedders`, with optional `vera.embedder_descriptors` metadata for
schema-driven Convert controls (`describe_embedding_providers` in the
sidecar). From Python, pass a custom `embedding_function`
to `vera_ingest.convert`, call `vera_doc.register_embedder`, or pass
`embedder_options={...}` / CLI `--embedder-option KEY=VALUE` for
provider-owned settings advertised by the provider's Options dataclass.
Advertised integer bounds are enforced (hashing `dimension` is 8–4096). See
[Creating an embedding provider plugin](creating-an-embedding-provider.md).
Prefer environment variables for API keys (`capabilities.credential_env` /
`preflight_embedder`); do not put secrets in Options. Desktop Convert calls
`preflight_embedder` before writing an archive. CLI `vera convert` and
`vera_ingest.convert()` do not call `preflight_embedder`; they resolve the
embedder with `get_embedder`, so missing credential env vars surface when
the factory runs. Convert-time knobs such
as `batch_size` use `scope: convert` so search can resolve
`get_embedder(stored_model_name)` with defaults.

### Official OpenAI embeddings

`vera-cli` and the desktop app bundle [`vera-embed-openai`](packages/vera-embed-openai.md).
Hashing remains the default. Set `OPENAI_API_KEY` (desktop: **File > Settings
→ Embeddings**):

```bash
set OPENAI_API_KEY=...
vera convert "input.pdf" --model openai:text-embedding-3-small \
  --embedder-option batch_size=64
```

The plugin records the full spec (for example
`openai:text-embedding-3-small`) as `model_name`, so later semantic searches
load the matching provider.

**Archives converted with a hosted embedder are not portable for semantic or
hybrid search.** Search resolves `get_embedder(stored_model_name)`, so a
recipient needs their own `OPENAI_API_KEY` and a reachable API. Keyword search
still works. Corpus search reports `skipped_semantic_model_groups` when the
query embedder cannot load.

OpenAI conversion bills per request. Desktop Convert Cancel does not interrupt
an in-flight embeddings HTTP batch; conversion checks cancellation after
`embed()` returns.

Optional `OPENAI_BASE_URL` (default `https://api.openai.com/v1`) points at
Azure, OpenRouter, or a local OpenAI-compatible server. Two archives can then
record the same `openai:<model-id>` while holding vectors from different
models; search cannot detect that. A separate `openai-compatible` provider
with a required explicit endpoint is out of scope.

Voyage and Ollama are not bundled. They need a query-versus-document hint on
`EmbeddingFunction` (`input_type` / `search_document:` prefixes); convert and
search share one `embed(texts)` today. See
[Creating an embedding provider plugin](creating-an-embedding-provider.md)
for the Options + descriptor authoring model.

Claude is an LLM rather than an embedding provider: Anthropic's Claude API has
no embeddings endpoint. A Claude application can use a separate provider such
as Voyage AI for retrieval embeddings, exposed through a plugin spec like
`voyage:voyage-3`.

## Chunking options

Chunking defaults are owned by each ingest pipeline. The default PyMuPDF
pipeline defaults to:

- `--chunk-size 500`
- `--overlap 75`

Legacy aliases are forwarded only when the selected pipeline advertises those
fields. Example for PyMuPDF:

```bash
vera convert "input.pdf" --chunk-size 700 --overlap 100
```

Equivalent provider-owned form (wins over the aliases):

```bash
vera convert "input.pdf" \
  --pipeline-option chunk_size=700 \
  --pipeline-option overlap=100
```

With PyMuPDF, chunks never span pages, preserving page-precise citations.
Larger chunks carry more context but may reduce retrieval precision; smaller
chunks are more specific but may separate related clauses. Sliding-window
helpers clamp overlap to `chunk_size - 1` so carry never overruns, even when
PyMuPDF's advertised overlap maximum (1000) is larger than the selected
`chunk_size`. Evaluate changes against a representative query set before
adopting non-default values.

## Pipeline options

Shared conversion accepts an opaque `pipeline_options` mapping. Each installed
pipeline owns typed defaults, validation, and a descriptor of supported fields.
Integer options are rejected when they fall outside the advertised `minimum`
and `maximum` (PyMuPDF/Docling `chunk_size` is 100–3000). `vera convert`
exposes that mapping as repeatable `--pipeline-option KEY=VALUE` flags. Digit-only
tokens become ints and boolean words become bools; dotted tokens such as `3.10`
stay strings and are not parsed as floats. Typed `from_mapping` validation then
checks each key.

```bash
vera convert "input.pdf" --parser pymupdf \
  --pipeline-option chunk_size=500 \
  --pipeline-option overlap=75 \
  --pipeline-option ocr_mode=auto
```

Compatibility aliases (`--chunk-size`, `--overlap`, `--ocr`, `--ocr-language`,
`--ocr-dpi`) still work for pipelines that accept them. Descriptor fields and
OCR engine determine which aliases are forwarded: Docling does **not** receive
`overlap`, `ocr_dpi`, `ocr_download`, or the Tesseract `--ocr-language` /
`ocr_language` alias. Explicit `--pipeline-option` / `pipeline_options` always
override aliases for the same key.

| Pipeline | Defaults | Notes |
| --- | --- | --- |
| PyMuPDF (`pymupdf`) | `chunk_size=500` words, `overlap=75` words, `ocr_mode=auto`, `ocr_language=eng`, `ocr_dpi=300`, `ocr_download=false` | Sliding-window chunks of whitespace-split words (`str.split()`, not characters or LLM subword tokens); Tesseract OCR; language picker lists bundled/downloadable codes |
| Docling (`docling`) | `chunk_size=500` whitespace tokens, `ocr_mode=auto`, `ocr_language=en`, `pdf_backend=docling_parse` | No `overlap` / `ocr_dpi` / Tesseract `--ocr-language` aliases; RapidOCR; auto page recovery / `pypdfium2` fallback on memory errors, then page-batch `pypdfium2` |

Discover descriptors from Python with `describe_ingest_pipeline` /
`list_ingest_pipeline_descriptors`, or from the desktop sidecar action
`describe_ingest_pipelines`.

## Ingest pipelines

`--parser` accepts an ingest pipeline spec `provider[:variant]`. The default
provider is `pymupdf` (from `vera-ingest-pymupdf`, installed with the CLI and
desktop app):

```bash
vera convert "input.pdf" --parser pymupdf
```

Install the official Docling extra for layout-aware HybridChunker output.
The package depends on Docling's `rapidocr` extra so RapidOCR and
`onnxruntime` are available for OCR:

```bash
pip install "vera-cli[docling]>=0.3.0"
# or from a checkout:
uv sync --extra docling
# or: python -m pip install vera-ingest-docling
vera convert "input.pdf" --parser docling
vera convert "input.pdf" --parser docling:hybrid
```

Unknown pipeline names fail before parsing with an install-the-plugin message;
VERA never silently falls back to PyMuPDF. The packaged desktop app bundles
PyMuPDF and OpenAI embeddings in one sidecar; Docling is a CLI extra. Extra
pip plugins install into the same environment (`python -m pip install` or
`python -m pip install -e <clone>`).
The desktop Convert view persists `embedder_options` / `embedder_configs` and
gates conversion on `preflight_embedder` so an archive is never written with a
model Search cannot resolve. CLI convert still rejects unknown `--model` /
`--parser` values before parsing, but it does not call `preflight_embedder`.
Embedder `credential_env` secrets stay in the environment, not
Options. OpenAI embeddings ship as `vera-embed-openai`; Voyage and Ollama
do not.
On Docling memory errors
(`bad_alloc`), VERA retries failed pages with a fresh converter and falls back
to the `pypdfium2` PDF backend when needed (whole document, then page batches
if that still raises); conversion rejects only when that
recovery is exhausted. Force the low-memory backend with
`--pipeline-option pdf_backend=pypdfium2`. Docling's descriptor advertises
`chunk_size` (HybridChunker limit in whitespace-split words), `ocr_mode`, `ocr_language`, and
`pdf_backend` — legacy `--overlap`, `--ocr-dpi`, `--ocr-allow-download`, and
the Tesseract `--ocr-language` alias are not forwarded.

Docling's `ocr_language` expects a **RapidOCR-native** code (for example
`en`, `fr`, `cyrillic`); VERA does not translate Tesseract-style codes for
it, so PyMuPDF's `eng` is not a valid value here. The shared `--ocr-language`
CLI default (`eng`) is a Tesseract/PyMuPDF alias and is **not** forwarded to
Docling, so `convert(..., parser="docling")` and `vera convert --parser docling`
resolve OCR language to Docling's own default `en`. To use another RapidOCR
code, pass `--pipeline-option ocr_language=fr` (or `pipeline_options=`).
Docling layout models run without `torch.compile` (so Windows does not need
Visual Studio's `cl.exe`).

First Docling conversion may download layout model artifacts from Hugging
Face. RapidOCR ONNX weights ship with `docling[rapidocr]` (VERA pins those
paths even when `DOCLING_ARTIFACTS_PATH` is set). An **empty or incomplete**
artifacts directory is not treated as offline — VERA lets Hugging Face
download or resume, and keeps Hub files under that cache via `HF_HOME`.
Stopping mid-download does not abort Hugging Face immediately; the next
run resumes. The first prefetch is about 380 MB (Heron ONNX plus TableFormer
accurate). The 0.3.0 desktop app does not run `prepare_docling` or list
**Advanced layout (slower)**; use `vera convert --parser docling` after
installing `vera-cli[docling]`. Set `DOCLING_ARTIFACTS_PATH` for a local
layout-model cache. Convert uses that ONNX layout engine instead of downloading a
second Transformers Heron snapshot and TableFormer fast. In CLI runs,
sidecar Hub progress appears as tqdm on stderr. After the cache is ready the
converter initializes. The Convert UI is
schema-driven: the sidecar
`describe_ingest_pipelines` action supplies descriptors, and
`PipelineConfigForm` renders only the fields each pipeline advertises under a
collapsed **Advanced pipeline options** section. For PyMuPDF, **OCR language**
is a dropdown of bundled and downloadable Tesseract codes (for example
`Spanish (spa)`), with a **Custom…** option for combinations such as
`eng+spa` or a manually installed `TESSDATA_PREFIX` code.

## Storing the source PDF

The original PDF is stored by default, enabling later export and document
viewing. To omit it:

```bash
vera convert "input.pdf" --store-original false
```

An archive created this way remains searchable, but:

- `vera export` cannot restore the source;
- validation reports the missing original document as a warning;
- viewers cannot obtain the original PDF from the archive.

## Verify conversion

After conversion:

```bash
vera inspect "output.vera" --json
vera validate "output.vera" --json
```

Inspect confirms the source, page and chunk counts, parser, and embedding
model. Validate checks SQLite integrity, required tables and metadata,
embedding counts, FTS consistency, and the stored source document.

## Python equivalent

```python
from vera_ingest import convert

path = convert(
    "input.pdf",
    "output.vera",
    parser="pymupdf",
    pipeline_options={"chunk_size": 700, "ocr_mode": "force"},
    model="hashing",
    # embedder_options={"device": "cpu"},
    # Compatibility aliases (forwarded when the pipeline advertises them):
    # chunk_size=500, overlap=75, ocr_mode="auto", ocr_language="eng",
)
print(path)
```

New callers should pass `parser`, `pipeline_options`, and embedder settings
(`model` / `embedding_function` / `embedder_options`). Pipelines receive a thin
`IngestRequest` whose `pipeline_options` dict carries provider-owned settings.
The legacy kwargs remain compatibility aliases. Omitted aliases mean the
pipeline's own default; the CLI still passes its argparse defaults. See
[Python API](python-api.md)
for more.
