# vera-doc

`vera-doc` publishes the `vera` Python package. It owns the portable SQLite
format implementation, typed records, transactional CRUD, embeddings, search,
corpus queries, and rebuildable library indexes.

It intentionally does **not** parse PDFs, perform OCR, provide the CLI, expose
MCP tools, or implement the desktop application.

## Install

```bash
python -m pip install ./packages/vera-doc
```

Python 3.10 or newer is required. The default hashing embedder works locally
without a model download or API key. Neural embeddings are available through
the optional `ml` extra.

## Start here

```python
from vera import ChunkRecord, VeraDatabase

with VeraDatabase.create("knowledge.vera") as database:
    database.add([
        ChunkRecord(
            id="chunk-1",
            text="The minimum pipe diameter is 12 inches.",
            metadata={"source_filename": "manual.pdf", "page_start": 42},
        )
    ])

with VeraDatabase.open("knowledge.vera") as database:
    results = database.search(text="minimum pipe size", top_k=5)
```

## Documentation

- [Concepts](../concepts/overview.md) — archives, records, search modes, and indexes.
- [Basic usage](../guides/basic-usage.md) — direct database and read-facade workflows.
- [Search documents](../searching.md) — semantic, keyword, and hybrid retrieval.
- [Document libraries](../document-libraries.md) — corpus search and persistent indexes.
- [Figures and regions](../figures-and-regions.md) — citation and viewer metadata.
- [Validation and export](../validation-and-export.md) — integrity checks and stored sources.
- [Python API guide](../python-api.md) — complete CRUD and search examples.
- [Runnable example](../examples/basic-example.md).

## API reference

- [Public package exports](../reference/vera.md)
- [VeraDatabase](../reference/vera-database.md)
- [Records and results](../reference/vera-models.md)
- [VeraDocument](../reference/vera-document.md)
- [VeraCorpus](../reference/vera-corpus.md)
- [Library indexes](../reference/vera-collection.md)
