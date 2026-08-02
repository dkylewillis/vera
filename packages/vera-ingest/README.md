# vera-ingest

`vera-ingest` contains VERA's source ingestion pipeline: PDF parsing, table
extraction, selective OCR, heading detection, chunking, and conversion.

It emits ready-made `vera.ChunkRecord` values and optional opaque attachments,
then stores them through `vera.VeraDocument`. It also provides
`vera_ingest.viewer` helpers that interpret ingest-produced page, figure,
region, and source-document conventions.

## Install

```bash
python -m pip install "vera-ingest>=0.2.2"
```

See the [vera-ingest documentation](https://dkylewillis.github.io/vera/packages/vera-ingest/)
for concepts, examples, and API reference.

See the [conversion guide](https://github.com/dkylewillis/vera/blob/main/docs/conversion.md).
