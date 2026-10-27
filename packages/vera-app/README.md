# vera-app

`vera-app` contains the Electron/React desktop application and its Python
sidecar. It composes `vera-doc` for storage/search with `vera-ingest` and
`vera-ingest-pymupdf` for conversion, and `vera-embed-openai` for hosted
OpenAI embeddings.

The Convert view is schema-driven: the sidecar `describe_ingest_pipelines`
action returns pipeline descriptors, and `PipelineConfigForm` renders only the
fields each pipeline advertises. Source-run and packaged builds use one sidecar
interpreter with PyMuPDF, hashing, Local semantic (MiniLM) via ONNX
Runtime, and OpenAI embeddings. The Windows installer vendors a VERA-exported MiniLM graph (no
PyTorch). Docling remains
a CLI extra (`vera[docling]`) and is not listed in Convert.

Packaged Windows installs register `.vera` archives and the `vera://` sign-in
link. Shell activation from File Explorer or the desktop opens the archive in
Document Preview as a standalone document and reuses the running VERA instance
when one exists. Shell-open does not persist the archive's parent as a library.
Convert defaults to local MiniLM (`sentence-transformers:all-MiniLM-L6-v2`);
hashing stays in the dropdown. The CLI default embedder is still hashing.

See the [vera-app documentation](https://dkylewillis.github.io/vera/packages/vera-app/)
for installation, user workflows, and architecture.

See the [desktop application guide](https://github.com/dkylewillis/vera/blob/main/docs/desktop-app-getting-started.md).
