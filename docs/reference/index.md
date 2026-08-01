# API Reference

This section documents the curated public Python API for VERA. Pages are
generated from source docstrings using [mkdocstrings](https://mkdocstrings.github.io/).

## Packages

| Package | Import | Purpose |
|---------|--------|---------|
| [vera-doc](vera.md) | `import vera` | Storage, CRUD, search, corpus, library indexes |
| [vera-ingest](vera-ingest.md) | `import vera_ingest` | PDF parsing, chunking, conversion |
| [vera-cli](vera-cli.md) | `import vera_cli` | Command-line interface |
| [vera-mcp](vera-mcp.md) | `import vera_mcp` | MCP server for AI agents |

Install packages from PyPI:

```bash
python -m pip install "vera-doc>=0.2.1"
python -m pip install "vera-ingest>=0.2.1"
python -m pip install "vera-cli>=0.2.1"
python -m pip install "vera-mcp>=0.2.1"
```

Or from a repository checkout:

```bash
python -m pip install ./packages/vera-doc
python -m pip install ./packages/vera-ingest
python -m pip install ./packages/vera-cli
python -m pip install ./packages/vera-mcp
```

## Where to start

=== "Create and search chunks"

    Use [`VeraDocument`](vera-document.md) with [`ChunkRecord`](vera-models.md)
    when your application already has final text.

=== "Open an existing archive"

    Use [`VeraDocument.open()`](vera-document.md) for search, inspection,
    figures, pages, highlight regions, and write-mode CRUD.

=== "Convert PDFs"

    Use [`vera_ingest.convert`](vera-ingest.md) or the `vera convert` CLI
    command.

=== "Search a folder"

    Use [`VeraCorpus`](vera-corpus.md) with
    [`build_library_index`](vera-collection.md) for multi-document retrieval.

## Exceptions

| Exception | Raised when |
|-----------|-------------|
| `DuplicateRecordError` | `add()` receives an ID that already exists |
| `RecordNotFoundError` | A requested chunk or attachment does not exist |
| `ReadOnlyError` | A write is attempted on a read-only database |

## Related documentation

- [Python API guide](../python-api.md) — narrative walkthrough with examples.
- [CLI reference](../cli-reference.md) — command-line flags and JSON output.
- [Format specification](../vera-spec-v0.2.md) — on-disk archive schema.
