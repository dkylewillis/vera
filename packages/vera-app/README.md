# vera-app

`vera-app` contains the Electron/React desktop application and its Python
sidecar. It composes `vera-doc` for storage/search with `vera-ingest` for
conversion.

The Convert view is schema-driven: the sidecar `describe_ingest_pipelines`
action returns pipeline descriptors, and `PipelineConfigForm` renders only the
fields each pipeline advertises (so Docling omits overlap/DPI while PyMuPDF
shows them).

See the [vera-app documentation](https://dkylewillis.github.io/vera/packages/vera-app/)
for installation, user workflows, and architecture.

See the [desktop application guide](https://github.com/dkylewillis/vera/blob/main/docs/desktop-app-getting-started.md).
