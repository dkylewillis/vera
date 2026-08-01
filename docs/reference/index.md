# API Reference

This section documents the curated public Python API for VERA. Pages are
generated from source docstrings using [mkdocstrings](https://mkdocstrings.github.io/).

## Packages

| Package | Import | Purpose |
|---------|--------|---------|
| [vera-doc](vera.md) | `import vera` | Storage, CRUD, search, corpus, library indexes |
| [vera-extract](vera-extract.md) | `import vera_extract` | PDF parsing, chunking, conversion |
| [vera-cli](vera-cli.md) | `import vera_cli` | Command-line interface |
| [vera-mcp](vera-mcp.md) | `import vera_mcp` | MCP server for AI agents |

Install packages individually or from the monorepo workspace:

```bash
python -m pip install ./packages/vera-doc
python -m pip install ./packages/vera-extract
python -m pip install ./packages/vera-cli
python -m pip install ./packages/vera-mcp
```

## Where to start

=== "Create and search chunks"

    Use [`VeraDatabase`](vera-database.md) with [`ChunkRecord`](vera-models.md)
    when your application already has final text.

=== "Open an existing archive"

    Use [`VeraDocument`](vera-document.md) for read-only search with figures,
    pages, and highlight regions. Use `VeraDatabase.open()` for direct CRUD.

=== "Convert PDFs"

    Use [`vera_extract.convert`](vera-extract.md) or the `vera convert` CLI
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
