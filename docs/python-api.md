# Python API

Install the core document package:

```bash
python -m pip install vera-doc
```

The `vera` package exposes conversion, document access, corpus search, and
collection-index helpers.

## Convert documents

```python
from vera import convert

output = convert(
    "input.pdf",
    "output.vera",
    model="hashing",
    parser="pymupdf",
    chunk_size=500,
    overlap=75,
    store_original=True,
)
```

`convert()` returns the output path as a string.

Batch conversion:

```python
from vera import batch_convert

report = batch_convert(
    "./pdf-library",
    recursive=True,
    overwrite=False,
    model="hashing",
)
print(report["converted"], report["skipped"], report["failed"])
```

Batch conversion continues after per-file failures and returns a report with
outputs, skipped paths, and errors.

## Open a document

```python
from vera import VeraDocument

doc = VeraDocument.open("manual.vera")
try:
    print(doc.inspect())
finally:
    doc.close()
```

`VeraDocument` does not currently implement the context-manager protocol, so
call `close()` explicitly, preferably in `finally`.

## Search

```python
doc = VeraDocument.open("manual.vera")
try:
    results = doc.search(
        "stormwater detention requirements",
        mode="hybrid",
        top_k=5,
        context_chunks=1,
    )
    for result in results:
        print(result.score, result.page_start, result.heading_path)
        print(result.text)
finally:
    doc.close()
```

`SearchResult` fields:

- `chunk_id: str`
- `score: float`
- `text: str`
- `page_start: int | None`
- `page_end: int | None`
- `heading_path: str | None`
- `source_filename: str | None`
- `document_id: str`
- `before_chunks` and `after_chunks` when context was requested

Call `result.as_dict()` for a JSON-ready dictionary.

Valid modes are `semantic`, `keyword`, and `hybrid`. `top_k` and
`context_chunks` must be non-negative.

## Inspect and validate

```python
doc = VeraDocument.open("manual.vera")
try:
    info = doc.inspect()
    validation = doc.validate()
finally:
    doc.close()
```

`inspect()` returns metadata and page, chunk, and embedding counts.
`validate()` returns the same report shape used by `vera validate --json`.

## Pages, blocks, and assets

```python
doc = VeraDocument.open("manual.vera")
try:
    page = doc.get_page(1)
    blocks = doc.get_blocks(page_number=1)
    asset = doc.get_asset("asset_block_000371", include_data=False)
finally:
    doc.close()
```

`get_page()` uses 1-based page numbers and returns `None` for a missing page.
The returned page contains `page_id`, `page_number`, `width`, `height`, and
`text`.

`get_blocks()` returns blocks in reading order. Each block contains
`block_id`, `page_number`, `block_type`, `text`, `bbox`, `heading_level`, and
`sort_order`.

`get_asset()` returns `None` for an unknown ID. Set `include_data=False` to
avoid loading the asset bytes.

## Figures and regions

List figures in a page range:

```python
doc = VeraDocument.open("manual.vera")
try:
    figures = doc.figures(page_start=10, page_end=20)
finally:
    doc.close()
```

Resolve a search result:

```python
doc = VeraDocument.open("manual.vera")
try:
    result = doc.search("pipe sizing chart", top_k=1)[0]
    figures = doc.figures_for(result, include_data=True)
    regions = doc.regions_for(result)
    same_regions = doc.get_chunk_regions(result.chunk_id)
finally:
    doc.close()
```

See [Figures and highlight regions](figures-and-regions.md) for object shapes
and coordinates.

## Original source document

```python
doc = VeraDocument.open("manual.vera")
try:
    source = doc.get_source_document()
    print(source.filename, source.mime_type, source.hash, len(source.data))
    path = doc.export_source_document("./exports")
finally:
    doc.close()
```

`SourceDocument` contains `filename`, `mime_type`, `data`, and `hash`.
Access and export raise `ValueError` if conversion omitted the source.

## Search a corpus

`VeraCorpus` supports a context manager:

```python
from vera import VeraCorpus

with VeraCorpus.open(
    "./library",
    recursive=True,
    excludes=["archive/**"],
    max_open_documents=16,
) as corpus:
    print(corpus.inspect())
    print(corpus.uses_index, corpus.index_status)

    results = corpus.search(
        "termination clause",
        mode="hybrid",
        top_k=10,
        context_chunks=1,
    )
    for result in results:
        print(result.file, result.page_start, result.text[:100])
```

`CorpusSearchResult` extends `SearchResult` with `file`, the source archive
path. `VeraCorpus.open()` automatically uses a fresh compatible collection
index unless `use_index=False`.

Build a corpus from explicit paths:

```python
with VeraCorpus.from_paths(["a.vera", "b.vera"]) as corpus:
    results = corpus.search("insurance requirements")
```

Use `corpus.figures_for(result)` and `corpus.regions_for(result)` for corpus
results.

## Build and inspect a collection index

```python
from vera import (
    build_library_index,
    library_index_status,
    update_library_index,
)

report = build_library_index(
    "./library",
    recursive=True,
    excludes=["archive/**"],
)
status = library_index_status("./library")
updated = update_library_index("./library")
```

These functions return the same report dictionaries used by the corresponding
CLI commands. Building and updating write `.vera-index/`.

`VeraCollectionIndex` is also public for callers that need low-level
`relative_path`, `chunk_id`, and score hits. Most applications should prefer
`VeraCorpus`, which resolves hits into complete `CorpusSearchResult` objects.

## Retrieval evaluation

The evaluation module is importable separately:

```python
from vera.evaluate import evaluate

summary = evaluate(
    "manual.vera",
    "queries.json",
    mode="all",
    top_k=5,
)
```

See [Examples and recipes](examples.md) for the query-file format.

## Public exports

The top-level `vera` package exports:

- `convert`, `batch_convert`
- `VeraDocument`, `SearchResult`, `SourceDocument`
- `VeraCorpus`, `CorpusSearchResult`
- `VeraCollectionIndex`
- `build_library_index`, `update_library_index`, `library_index_status`
