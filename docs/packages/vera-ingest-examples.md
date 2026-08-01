# vera-ingest examples

These examples use the public `vera_ingest` API directly. For equivalent
shell workflows, use [`vera convert`](vera-cli.md).

## Convert one PDF

```python
from vera_ingest import convert

output = convert(
    "manual.pdf",
    "manual.vera",
    model="hashing",
    chunk_size=500,
    overlap=75,
    store_original=True,
    ocr_mode="auto",
)
print(output)
```

The function returns the output path after validating and atomically publishing
the archive.

## Force OCR

```python
from vera_ingest import convert

convert(
    "scanned-manual.pdf",
    "scanned-manual.vera",
    ocr_mode="force",
    ocr_language="eng",
    ocr_dpi=300,
)
```

Use forced OCR only when automatic detection misses scanned content.

## Convert a directory

```python
from vera_ingest import batch_convert

report = batch_convert(
    "./proposals",
    recursive=True,
    model="hashing",
    ocr_mode="auto",
)

print("converted:", report["converted"])
print("failed:", report["failed"])
print("malformed existing:", report["malformed_existing"])
```

Batch conversion continues after per-file failures. Check both `failed` and
`malformed_existing` before treating the batch as successful.

See [Convert documents](../conversion.md) for every supported option and its
filesystem behavior.
