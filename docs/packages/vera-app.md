# vera-app

`vera-app` is the VERA desktop product: an Electron and React interface backed
by a local Python sidecar. It composes `vera-doc` for retrieval and
`vera-extract` for conversion; it does not use the CLI as its backend.

The Python package root intentionally exports no public API. Sidecar, LLM
provider, mode, and cancellation modules are implementation details and are
therefore documented in the architecture guide rather than generated as public
API reference.

## Install the Windows app

Download `VERA Setup <version>.exe` from the
[latest GitHub Release](https://github.com/dkylewillis/vera/releases/latest).

## First workflow

1. Open **Convert PDF** and convert one PDF or a directory.
2. Use **File > Open Folder** to activate a document library.
3. Open **Search** for fully local hybrid retrieval.
4. To use **Ask**, configure a provider under **File > LLM Providers**.
5. Select a citation in an answer to inspect the highlighted source passage.

Search and conversion do not require a model-provider account. A provider is
only required for generated Ask responses.

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

The supported packaged target is currently Windows. Use the CLI for Sentence
Transformers embedding models or explicit OCR controls.
