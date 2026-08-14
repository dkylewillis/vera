# vera-app

`vera-app` contains the Electron/React desktop application and its Python
sidecar. It composes `vera-doc` for storage/search with `vera-ingest` and
`vera-ingest-pymupdf` for conversion.

The Convert view is schema-driven: the sidecar `describe_ingest_pipelines`
action returns pipeline descriptors, and `PipelineConfigForm` renders only the
fields each pipeline advertises (so Docling omits overlap/DPI while PyMuPDF
shows them). Source-run and packaged builds keep PyMuPDF in the sidecar and
run extra ingest plugins from a trusted external Python environment via
`vera_plugin_host`.

See the [vera-app documentation](https://dkylewillis.github.io/vera/packages/vera-app/)
for installation, user workflows, and architecture.

See the [desktop application guide](https://github.com/dkylewillis/vera/blob/main/docs/desktop-app-getting-started.md).
