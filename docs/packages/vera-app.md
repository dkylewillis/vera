# vera-app

`vera-app` is the VERA desktop product: an Electron and React interface backed
by a local Python sidecar. It composes `vera-doc` for retrieval,
`vera-ingest` / `vera-ingest-pymupdf` for PDF conversion (Markdown ingest is
bundled in `vera-ingest`), and `vera-embed-openai`
for hosted OpenAI embeddings; it does not use the CLI as its backend.
`vera-ingest-docling` is an optional CLI extra, not bundled in the installer.

See the [product overview](../desktop-app-overview.md) for the intended
workflow and audience.

The Python package root intentionally exports no public API. Sidecar, LLM
provider, mode, and cancellation modules are implementation details and are
therefore documented in the architecture guide rather than generated as public
API reference.

## Install the Windows app

Download `VERA Setup <version>.exe` from the
[latest GitHub Release](https://github.com/dkylewillis/vera/releases/latest).

## First workflow

1. Open **Convert** and convert selected PDFs or Markdown files, or a directory, or
   right-click a folder and choose **Convert…**. Expand
   **Advanced pipeline options** for schema-driven settings from
   `describe_ingest_pipelines` / `PipelineConfigForm`. Convert lists PyMuPDF
   and the bundled Markdown pipeline. Convert embedding presets are hashing
   (default), **Local semantic
   (MiniLM)**, and OpenAI `text-embedding-3-*`. MiniLM is ONNX Runtime under the same
   `sentence-transformers/all-MiniLM-L6-v2` identity, and the installer
   vendors a VERA-exported, SHA256-pinned graph. Save `OPENAI_API_KEY` under
   **File > Settings → Embeddings**. Archives converted with OpenAI are not
   portable for semantic search. Right-click a `.vera`
   archive and choose **Reconvert…** to replace it with a different ingest
   pipeline or embedding model.
2. Use **File > Open Folder** to activate a document library.
3. Open **Search** for fully local hybrid retrieval.
4. To use **Ask**, configure a provider under **File > Settings → LLM Providers**.
5. Optional: save a Hugging Face token under **File > Settings → Hugging
   Face** (or set `HF_TOKEN`) for Hub model downloads used by some converters
   and embedders. **File > Open convert log...** (or Convert **Open log** /
   **Settings → Diagnostics**) opens `userData/logs/sidecar.log` for timed
   convert steps.
6. Select a citation in an answer to inspect the highlighted source passage.

Search and conversion do not require a model-provider account unless you
choose a hosted embedder such as OpenAI. A Chat provider is only required
for generated Ask responses.

Source-run and packaged conversions use one sidecar interpreter with PyMuPDF,
hashing, ONNX MiniLM, and OpenAI embeddings. Extra ingest and embedding
plugins are pip packages in that
same environment (`python -m pip install` or `python -m pip install -e
<clone>`). See
[Creating an ingest pipeline plugin](../creating-an-ingest-pipeline.md),
[Creating an embedding provider](../creating-an-embedding-provider.md), and
[Desktop app architecture](../desktop-app-architecture.md).

## Documentation

- [Run and package the desktop app](../desktop-app-getting-started.md).
- [Desktop app architecture](../desktop-app-architecture.md) — Electron,
  renderer, sidecar protocol, and process boundaries.
- [Document libraries](../document-libraries.md) — index behavior shared with
  the desktop app.
- [Search documents](../searching.md).
- [General troubleshooting](../troubleshooting.md).

## Developer entry point

```bash
npm run app:install
npm run app:dev
```

The supported packaged target is currently Windows. Use the CLI
`--pipeline-option` flags (or Convert-view pipeline settings) for
provider-owned chunking and OCR controls. Packaged and `app:dev` Convert both
report `pymupdf`, plus hashing and MiniLM embedders. `app:dev` vendors MiniLM
into `packages/vera-app/build/minilm` before launch; packaged
builds vendor a VERA-exported ONNX graph. The sidecar does not import Torch.
Docling is not listed;
use `vera-cli[docling]` from the CLI.
