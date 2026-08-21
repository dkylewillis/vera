# vera-app

`vera-app` is the VERA desktop product: an Electron and React interface backed
by a local Python sidecar. It composes `vera-doc` for retrieval and
`vera-ingest` / `vera-ingest-pymupdf` for conversion;
it does not use the CLI as its backend. `vera-ingest-docling` is an optional
CLI extra, not bundled in the installer.

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

1. Open **Convert PDF** and convert selected PDFs or a directory, or
   right-click a folder and choose **Convert PDFs…**. Expand
   **Advanced pipeline options** for schema-driven settings from
   `describe_ingest_pipelines` / `PipelineConfigForm`. Convert lists PyMuPDF
   as the 0.3.0 ingest pipeline. Convert embedding presets are hashing
   (default) and **Local semantic
   (MiniLM)**; MiniLM weights ship in the
   Windows installer. Hosted embedders
   are a 0.3.1 follow-up. Right-click a `.vera`
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

Search and conversion do not require a model-provider account. A provider is
only required for generated Ask responses.

Source-run and packaged conversions use one sidecar interpreter with PyMuPDF,
hashing, and Sentence Transformers MiniLM. Extra ingest and embedding
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
report `pymupdf`, plus hashing and MiniLM embedders. `app:dev` loads MiniLM
from `packages/vera-app/build/minilm` when that snapshot exists; packaged
builds vendor it. The sidecar imports Torch on the main thread at start so
Convert does not deadlock on Windows. Docling is not listed;
use `vera-cli[docling]` from the CLI.
