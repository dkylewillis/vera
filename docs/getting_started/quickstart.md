# Quickstart

This guide walks through a complete workflow: convert a PDF, validate the
archive, search it, and retrieve results from Python.

## Prerequisites

- Python 3.10 or newer
- VERA installed from source (see [Getting started](../getting-started.md))
- A local PDF to convert

## Step 1 — Convert a PDF

```bash
vera convert "manual.pdf" "manual.vera"
```

From Python:

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

```bash
vera inspect "manual.vera" --json
vera validate "manual.vera" --json
```

## Step 3 — Search from the CLI

```bash
vera search "manual.vera" "stormwater detention requirements" \
  --mode hybrid \
  --top-k 5 \
  --json
```

## Step 4 — Search from Python

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
            print(result.score, result.page_start, result.heading_path)
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

```bash
vera convert "./library" --recursive
vera index build "./library" --recursive
vera search "./library" "termination clause" --top-k 10 --json
```

## Next steps

- [Search guide](../searching.md) — modes, filters, and query patterns.
- [Document libraries](../document-libraries.md) — indexing large collections.
- [Database API](../reference/database.md) — generated Python reference.
