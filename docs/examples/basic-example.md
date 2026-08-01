# Basic example

This example creates a `.vera` archive from ready-made chunks, searches it with
all three modes, and prints citation-ready output. It uses only `vera-doc` — no
PDF or OCR dependencies.

## Create and search a database

```python
"""Minimal vera-doc example: create, populate, and search an archive."""

from vera import ChunkRecord, QueryResult, VeraDatabase


def print_result(result: QueryResult) -> None:
    meta = result.record.metadata
    page = meta.get("page_start", "?")
    heading = meta.get("heading_path", "")
    print(f"  score={result.score:.3f}  page={page}  {heading}")
    print(f"  {result.record.text}\n")


records = [
    ChunkRecord(
        id="pipe-1",
        text="The minimum pipe diameter is 12 inches for all storm drains.",
        metadata={
            "source_filename": "manual.pdf",
            "page_start": 42,
            "heading_path": "Chapter 4 > Pipe Design",
        },
    ),
    ChunkRecord(
        id="detention-1",
        text=(
            "Detention basins are required when the impervious area "
            "exceeds one acre."
        ),
        metadata={
            "source_filename": "manual.pdf",
            "page_start": 117,
            "heading_path": "Chapter 4 > Detention Design",
        },
    ),
    ChunkRecord(
        id="section-4-2",
        text="Section 4.2 covers outlet structure sizing requirements.",
        metadata={
            "source_filename": "manual.pdf",
            "page_start": 88,
            "heading_path": "Chapter 4 > 4.2 Outlet Structures",
        },
    ),
]

# Create a new archive and add records.
with VeraDatabase.create("example.vera", metadata={"project": "drainage"}) as db:
    db.add(records)

# Search with each mode.
with VeraDatabase.open("example.vera") as db:
    print("=== keyword: exact section reference ===")
    for r in db.search(text="section 4.2", mode="keyword", top_k=3):
        print_result(r)

    print("=== semantic: paraphrased question ===")
    for r in db.search(text="how large should the pond be", mode="semantic", top_k=3):
        print_result(r)

    print("=== hybrid: general regulatory query ===")
    for r in db.search(text="detention requirements", mode="hybrid", top_k=3):
        print_result(r)

    # Inspect and validate.
    info = db.inspect()
    print(f"Archive: {info['chunks']} chunks, model={info['embedding_model']}")
    report = db.validate()
    assert report["ok"], report["issues"]
```

## Run it

Save the script as `basic_example.py` and run:

```bash
python basic_example.py
```

Expected output includes the section 4.2 chunk for the keyword query, the
detention basin chunk for the semantic and hybrid queries, and a validation
summary.

## Variations

- Add [attachments](../python-api.md#optional-attachments) to store the original
  PDF alongside chunks.
- Use [`vera_extract.convert`](../reference/conversion.md) to build archives
  from PDFs instead of hand-authored chunks.
- Open a folder of archives with [`VeraCorpus`](../reference/corpus.md) for
  multi-document search.

See [Examples and recipes](../examples.md) for CLI-based workflows.
