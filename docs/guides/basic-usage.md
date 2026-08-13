# Basic usage

This guide covers the common path: convert a PDF, inspect the archive, then
search it from the CLI or Python.

## Step 1 — Convert a PDF

```bash
vera convert manual.pdf manual.vera --model hashing
```

Directory conversion writes each `.vera` beside its source PDF:

```bash
vera convert ./proposals --recursive
```

## Step 2 — Inspect and validate

```bash
vera inspect manual.vera --json
vera validate manual.vera --json
```

## Step 3 — Search from the CLI

```bash
vera search manual.vera "stormwater detention requirements" --top-k 5 --json
```

Add `--context-chunks 1` for neighboring text, `--figures` for table/chart
metadata, or `--regions` for page bounding boxes.

## Step 4 — Search from Python

```python
from vera_doc import VeraDocument

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

Use `mode="write"` with `create()` / `add()` / `upsert()` when you already have
ready-made `ChunkRecord` objects and do not need PDF conversion.

## Step 5 — Search a document library

For a folder of `.vera` files, build an index once and search the corpus:

```bash
vera convert "./library" --recursive
vera index build "./library" --recursive
vera search "./library" "detention requirements" --top-k 5 --json
```

```python
from vera_doc import VeraCorpus, build_library_index

build_library_index("./library", recursive=True)

with VeraCorpus.open("./library") as corpus:
    results = corpus.search("detention requirements", top_k=5)
```
