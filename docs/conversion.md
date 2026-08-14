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

Automatic OCR is the default:

```bash
vera convert "scan.pdf" "scan.vera" --ocr auto
```

OCR runs only on pages that are mostly a scanned image and have too little
native text to search reliably. Blank pages are skipped. Mixed PDFs can
therefore use native extraction on ordinary pages and OCR on scanned pages in
one conversion.

Controls:

- `--ocr auto` selects scanned pages (default);
- `--ocr off` never invokes OCR;
- `--ocr force` OCRs every page, replacing native text extraction;
- `--ocr-language eng` selects Tesseract language data;
- `--ocr-dpi 300` controls recognition resolution.

VERA bundles the official `tessdata_fast` English model and passes it directly
to PyMuPDF's Tesseract integration. Default English OCR therefore works
offline without installing Tesseract or configuring the system. Other
languages are not bundled; install their `.traineddata` files and set
`TESSDATA_PREFIX` when selecting them with `--ocr-language`. OCR failures name
the page and language and preserve any existing destination.

OCR text is stored as ordinary paragraph blocks with page bounding boxes, so
search results and highlight regions work normally. This first OCR path targets
scanned prose. It does not reconstruct scanned tables, forms, or complex
multi-column reading order. Use an external layout-aware OCR tool for those
documents; optional ingest plugins can provide layout-aware parsers. See
[Creating an ingest pipeline plugin](creating-an-ingest-pipeline.md).

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

It is deterministic, local, and requires no machine-learning package.

For neural embeddings, install the optional dependency and name a
Sentence Transformers model:

```bash
python -m pip install "vera-cli>=0.2.5" "vera-doc[ml]>=0.2.5"
vera convert "input.pdf" --model sentence-transformers/all-MiniLM-L6-v2
```

The model name, vector dimension, and stored-vector normalization policy are
recorded in the archive. Both built-in embedders use L2 normalization. Search
uses the recorded model, so the `ml` extra must also be installed on machines
that search an archive created with a Sentence Transformers model.

Use only `hashing`, `vera-hashing-384`, `all-MiniLM-L6-v2`, or a
`sentence-transformers/...` name. An unrecognized model name falls
back to hashing while retaining the requested name in metadata; that can make
the archive difficult to query consistently on another machine.

## Chunking options

Defaults:

- `--chunk-size 500`
- `--overlap 75`

Example:

```bash
vera convert "input.pdf" --chunk-size 700 --overlap 100
```

Chunks never span pages, preserving page-precise citations. Larger chunks carry
more context but may reduce retrieval precision; smaller chunks are more
specific but may separate related clauses. Evaluate changes against a
representative query set before adopting non-default values.

## Parser

The bundled parser is `pymupdf`:

```bash
vera convert "input.pdf" --parser pymupdf
```

Additional parsers are discovered from installed packages that register the
`vera.ingest_pipelines` entry-point group:

```bash
python -m pip install vera-ingest-docling
vera convert "input.pdf" --parser docling
```

Cloned plugins need an editable install so entry points are visible:

```bash
python -m pip install -e ./my-vera-plugin
```

Unknown names fail before parsing and never fall back to another pipeline.

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
    chunk_size=500,
    overlap=75,
    store_original=True,
    ocr_mode="auto",
    ocr_language="eng",
    ocr_dpi=300,
)
print(path)
```

See [Python API](python-api.md) for more.
