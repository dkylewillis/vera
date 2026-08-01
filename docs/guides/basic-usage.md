# Basic usage

This guide walks through a complete workflow: convert a PDF, validate the
archive, search it, and retrieve results from Python.

## Prerequisites

- Python 3.10 or newer
- VERA installed from source (see [Getting Started](../getting-started.md))
- A local PDF to convert

## Step 1 — Convert a PDF

The CLI is the simplest path for PDF conversion:

```bash
vera convert "manual.pdf" "manual.vera"
```

This extracts native text, selectively OCRs image-based pages, chunks the
content, embeds it with the local `hashing` model, and validates the archive
before publishing it.

To convert from Python:

```python
from vera_extract import convert

output_path = convert(
    "manual.pdf",
    "manual.vera",
    model="hashing",
    ocr_mode="auto",
    store_original=True,
)
print(f"Created {output_path}")
```

## Step 2 — Inspect and validate

Confirm the archive is well-formed before relying on it:

```bash
vera inspect "manual.vera" --json
vera validate "manual.vera" --json
```

`validate` exits with code 0 when the archive passes all integrity checks.

## Step 3 — Search from the CLI

Hybrid search is the best default for natural-language questions:

```bash
vera search "manual.vera" "stormwater detention requirements" \
  --mode hybrid \
  --top-k 5 \
  --json
```

Add `--context-chunks 1` for neighboring text, `--figures` for table/chart
metadata, or `--regions` for page bounding boxes.

## Step 4 — Search from Python

Use `VeraDocument` when you need the read facade (figures, pages, regions) or
`VeraDatabase` for direct access:

=== "VeraDocument (read facade)"

    ```python
    from vera import VeraDocument

    with VeraDocument.open("manual.vera") as document:
        for result in document.search(
            "stormwater detention requirements",
            mode="hybrid",
            top_k=5,
            context_chunks=1,
        ):
            print(
                result.score,
                result.page_start,
                result.heading_path,
            )
            print(result.text[:200])
    ```

=== "VeraDatabase (direct API)"

    ```python
    from vera import VeraDatabase

    with VeraDatabase.open("manual.vera") as database:
        for result in database.search(
            text="stormwater detention requirements",
            mode="hybrid",
            top_k=5,
        ):
            print(result.score, result.record.metadata)
            print(result.record.text[:200])
    ```

## Step 5 — Search a document library

For a folder of `.vera` files, build an index once and search the corpus:

```bash
vera convert "./library" --recursive
vera index build "./library" --recursive
vera search "./library" "termination clause" --top-k 10 --json
```

From Python:

```python
from vera import VeraCorpus, build_library_index

build_library_index("./library", recursive=True)

with VeraCorpus.open("./library", recursive=True) as corpus:
    for result in corpus.search("termination clause", top_k=10):
        print(result.file, result.page_start, result.text[:100])
```

## Next steps

- [Search guide](../searching.md) — modes, filters, and query patterns.
- [Document libraries](../document-libraries.md) — indexing large collections.
- [API Reference](../reference/index.md) — full Python API documentation.
