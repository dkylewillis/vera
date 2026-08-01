# vera-extract

`vera-extract` contains VERA's source extraction pipeline: PDF parsing, table
extraction, selective OCR, heading detection, chunking, and conversion.

It emits ready-made `vera.ChunkRecord` values and optional opaque attachments,
then stores them through `vera.VeraDatabase`.

See the [vera-extract documentation](https://dkylewillis.github.io/vera/packages/vera-extract/)
for concepts, examples, and API reference.

See the [conversion guide](https://github.com/dkylewillis/vera/blob/main/docs/conversion.md).
