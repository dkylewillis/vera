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

Single-file conversion replaces an existing output path. Choose a different
output name if the existing archive must be preserved.

## Convert a directory

Directory conversion writes each archive beside its PDF:

```bash
vera convert "./proposals"
```

Discover nested PDFs:

```bash
vera convert "./proposals" --recursive
```

Existing archives are skipped by default. Replace them explicitly:

```bash
vera convert "./proposals" --recursive --overwrite
```

Do not provide a single output path for directory conversion.

For a machine-readable batch report:

```bash
vera convert "./proposals" --recursive --json
```

The report distinguishes discovered, converted, skipped, and failed files.
Batch conversion continues after an individual PDF fails and exits nonzero if
any conversion failed.

## Embedding models

The default model is `hashing`:

```bash
vera convert "input.pdf" --model hashing
```

It is deterministic, local, and requires no machine-learning package.

For neural embeddings, install the optional dependency and name a
Sentence Transformers model:

```bash
python -m pip install vera-cli "vera-doc[ml]"
vera convert "input.pdf" --model sentence-transformers/all-MiniLM-L6-v2
```

The model name and vector dimension are recorded in the archive. Search uses
the recorded model, so the `ml` extra must also be installed on machines that
search an archive created with a Sentence Transformers model.

Use only `hashing`, `vera-hashing-384`, `all-MiniLM-L6-v2`, or a
`sentence-transformers/...` name. In v0.1, an unrecognized model name falls
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

VERA v0.1 supports the `pymupdf` parser:

```bash
vera convert "input.pdf" --parser pymupdf
```

Other parser names currently fail.

## Storing the source PDF

The original PDF is stored by default, enabling later export and document
viewing. To omit it:

```bash
vera convert "input.pdf" --store-original false
```

An archive created this way remains searchable, but:

- `vera export` cannot restore the source;
- the current validator reports the missing original document as an issue;
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
from vera import convert

path = convert(
    "input.pdf",
    "output.vera",
    model="hashing",
    chunk_size=500,
    overlap=75,
    store_original=True,
)
print(path)
```

See [Python API](python-api.md) for more.
