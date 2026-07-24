# Inspect, validate, and export archives

VERA provides read-only inspection and validation commands plus an export
command for restoring the embedded source document.

## Inspect metadata

```bash
vera inspect "manual.vera"
```

Inspection reports the format version, source filename, page and chunk counts,
embedding model and dimensions, parser, and creation time.

For structured output:

```bash
vera inspect "manual.vera" --json
```

Metadata values stored by the format may be strings even when they look
numeric. Summary counts such as `pages`, `chunks`, and `embeddings` are
integers.

## Validate integrity

```bash
vera validate "manual.vera"
```

Validation checks:

- SQLite integrity;
- required tables and metadata;
- document, page, chunk, embedding, FTS, and asset counts;
- one embedding and one FTS row per chunk;
- embedding blob dimensions;
- page references;
- presence of the original source document.

JSON mode returns the full report:

```bash
vera validate "manual.vera" --json
```

The report includes `ok`, `issues`, `warnings`, `counts`, `checks`, and
`metadata`. Exit status is 0 when `ok` is true and 1 when validation finds an
issue. An invalid archive still emits the JSON report, so callers should retain
stdout when handling exit status 1.

An archive created with `--store-original false` is searchable, but the current
validator reports the missing original source as an issue.

## Export the original source

Export to the stored filename in the current directory:

```bash
vera export "manual.vera"
```

Choose a path:

```bash
vera export "manual.vera" "./exports/manual.pdf"
```

If the output names an existing directory, VERA writes the stored filename
inside that directory:

```bash
vera export "manual.vera" "./exports"
```

JSON mode reports the output path, stored filename, MIME type, and source hash:

```bash
vera export "manual.vera" "./exports" --json
```

If the archive does not contain the original source, export returns
`{"ok": false, "error": "..."}` and exits 1.

Export writes to disk and may create parent directories. Choose the destination
carefully.

## Python API

```python
from vera import VeraDocument

doc = VeraDocument.open("manual.vera")
try:
    info = doc.inspect()
    report = doc.validate()

    source = doc.get_source_document()
    print(source.filename, source.mime_type, source.hash)

    output = doc.export_source_document("./exports")
    print(output)
finally:
    doc.close()
```

`source.data` contains the original bytes. `get_source_document()` and
`export_source_document()` raise `ValueError` when no original source is
stored.

## Recovery guidance

Validation identifies damage but does not repair an archive. The safest
recovery is:

1. preserve the failing archive for diagnosis;
2. verify that the source PDF is available;
3. convert the source into a new output path;
4. validate the new archive;
5. replace the old archive only after confirming search behavior.

Do not edit the SQLite tables directly as a routine repair strategy.
