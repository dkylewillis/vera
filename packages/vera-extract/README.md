# vera-extract

`vera-extract` contains VERA's source extraction pipeline: PDF parsing, table
extraction, selective OCR, heading detection, chunking, and conversion.

It emits ready-made `vera.ChunkRecord` values and optional opaque attachments,
then stores them through `vera.VeraDatabase`.

See the [conversion guide](https://github.com/dkylewillis/vera/blob/main/docs/conversion.md).
