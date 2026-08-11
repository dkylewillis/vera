# Convert documents

`vera convert` turns PDFs into portable `.vera` archives. Conversion parses
page layout, detects headings and figures, creates citation-ready chunks,
computes embeddings, builds the FTS5 keyword index, and normally stores the
original PDF.

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
search reliably. Blank pages
are skipped. Mixed PDFs can therefore use native extraction on ordinary pages
and OCR on scanned pages in one conversion.

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
set. Codes match Tesseract's language list (for example `spa`, not `es`).
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

Existing archives are validated before they are skipped. A malformed existing
archive is reported separately and is not silently preserved as a successful
skip. Replace existing outputs explicitly:

```bash
vera convert "./proposals" --recursive --overwrite
```

Do not provide a single output path for directory conversion.

For a machine-readable batch report:

```bash
vera convert "./proposals" --recursive --json
```

The report distinguishes discovered, converted, valid existing skips,
malformed existing outputs, and conversion failures. `malformed_existing`
entries include `input`, `output`, and validation `issues`. Batch conversion
continues after an individual PDF fails and exits nonzero if any conversion
failed or malformed existing output was found.

## Embedding models

The default model is `hashing`:

```bash
vera convert "input.pdf" --model hashing
```

It is deterministic, local, and requires no machine-learning package. Equivalent
specs include `vera-hashing-384` and `hashing:vera-hashing-384`.

For neural embeddings, install the optional dependency and name a
Sentence Transformers model:

```bash
python -m pip install "vera-cli>=0.2.4" "vera-doc[ml]>=0.2.4"
vera convert "input.pdf" --model sentence-transformers:all-MiniLM-L6-v2
```

Legacy slash-form names such as `sentence-transformers/all-MiniLM-L6-v2` and the
bare alias `all-MiniLM-L6-v2` still work.

The model name, vector dimension, and stored-vector normalization policy are
recorded in the archive. Both built-in embedders use L2 normalization. Search
uses the recorded model, so the `ml` extra must also be installed on machines
that search an archive created with a Sentence Transformers model.

Prefer `provider:model-id` specs. An unrecognized provider or model raises an
error at convert time instead of silently falling back to hashing. Third-party
plugins can register providers under the Python entry-point group
`vera.embedders`. From Python, pass a custom `embedding_function` to
`vera_ingest.convert` or call `vera.register_embedder`.

### Hosted provider plugins

VERA does not bundle hosted embedding providers. Install a plugin that
registers the desired provider, then use its `provider:model-id` spec:

```bash
set OPENAI_API_KEY=...
vera convert "input.pdf" --model openai:text-embedding-3-small
```

The plugin's embedder must record the full spec (for example,
`openai:text-embedding-3-small`) as `model_name`, so later semantic searches
load the matching provider. See the
[OpenAI plugin example](../packages/vera-doc/README.md#openai-embedding-plugin-example)
for a complete entry-point implementation.

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
chunks are more specific but may separate related clauses. Evaluate changes
against a representative query set before adopting non-default values.

## Pipeline options

Shared conversion accepts an opaque `pipeline_options` mapping. Each installed
pipeline owns typed defaults, validation, and a descriptor of supported fields.
`vera convert` exposes that mapping as repeatable `--pipeline-option KEY=VALUE`
flags. Values are coerced to bool/int/float when unambiguous; otherwise they
remain strings.

```bash
vera convert "input.pdf" --parser pymupdf \
  --pipeline-option chunk_size=500 \
  --pipeline-option overlap=75 \
  --pipeline-option ocr_mode=auto
```

Compatibility aliases (`--chunk-size`, `--overlap`, `--ocr`, `--ocr-language`,
`--ocr-dpi`) still work. Descriptor fields determine which aliases are
forwarded: Docling does **not** receive `overlap` or `ocr_dpi`. Explicit
`--pipeline-option` / `pipeline_options` always override aliases for the same
key.

| Pipeline | Defaults | Notes |
| --- | --- | --- |
| PyMuPDF (`pymupdf`) | `chunk_size=500`, `overlap=75`, `ocr_mode=auto`, `ocr_language=eng`, `ocr_dpi=300`, `ocr_download=false` | Sliding-window character chunks; Tesseract OCR; language picker lists bundled/downloadable codes |
| Docling (`docling`) | `chunk_size=500` tokens, `ocr_mode=auto`, `ocr_language=en`, `pdf_backend=docling_parse` | No `overlap` / `ocr_dpi` fields; RapidOCR; auto page recovery / `pypdfium2` fallback on memory errors |

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

Install the optional Docling plugin for layout-aware HybridChunker output.
The plugin depends on Docling's `rapidocr` extra so RapidOCR and
`onnxruntime` are available for OCR:

```bash
uv sync --extra docling
# or: python -m pip install vera-ingest-docling
vera convert "input.pdf" --parser docling
vera convert "input.pdf" --parser docling:hybrid
```

Unknown pipeline names fail before parsing with an install-the-plugin message;
VERA never silently falls back to PyMuPDF. On Docling memory errors
(`bad_alloc`), VERA retries failed pages with a fresh converter and falls back
to the `pypdfium2` PDF backend when needed; conversion rejects only when that
recovery is exhausted. Force the low-memory backend with
`--pipeline-option pdf_backend=pypdfium2`. Docling's descriptor advertises
`chunk_size` (HybridChunker token limit), `ocr_mode`, `ocr_language`, and
`pdf_backend` — legacy `--overlap` and `--ocr-dpi` are not forwarded. Docling
uses RapidOCR rather than Tesseract, so VERA maps Tesseract-style language
codes such as `eng` to RapidOCR's `en` (and similarly for other common
aliases); Docling's own default language is `en`. Docling layout models run
without `torch.compile` (so Windows does not need Visual Studio's `cl.exe`).

First Docling conversion may download model artifacts. Set
`DOCLING_ARTIFACTS_PATH` for a local cache. Packaged desktop releases do not
bundle Docling; source-run apps can select installed pipelines in the Convert
view. The Convert UI is schema-driven: the sidecar
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
    model="hashing",
    parser="pymupdf",
    # Compatibility aliases (forwarded when the pipeline advertises them):
    chunk_size=500,
    overlap=75,
    store_original=True,
    ocr_mode="auto",
    ocr_language="eng",
    ocr_dpi=300,
    # Explicit provider-owned options win for matching keys:
    # pipeline_options={"chunk_size": 700, "ocr_mode": "force"},
)
print(path)
```

Pipelines receive a thin `IngestRequest` whose `pipeline_options` dict carries
provider-owned settings. Prefer `pipeline_options=` for new code; the legacy
kwargs remain compatibility aliases. See [Python API](python-api.md) for more.
