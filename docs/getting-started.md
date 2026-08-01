# Getting started

This tutorial installs the VERA CLI, converts one PDF into a portable `.vera`
archive, and searches it.

VERA is currently pre-1.0 and experimental. Preserve source documents and expect
format or API changes before a stable release.

## Requirements

- Python 3.10 or newer
- A local PDF
- Windows, macOS, or Linux

## Install from PyPI

Install the CLI and its dependencies:

```bash
python -m pip install "vera-cli>=0.2.1"
```

That installs `vera-doc` and `vera-ingest` as well. Add MCP support with:

```bash
python -m pip install "vera-cli[mcp]>=0.2.1"
```

Verify that the console script is available:

```bash
vera --help
```

If `vera` is not on `PATH`, invoke the same CLI as a Python module:

```bash
python -m vera_cli --help
```

### Library-only installs

```bash
# Storage and search only
python -m pip install "vera-doc>=0.2.1"

# PDF conversion and viewer helpers
python -m pip install "vera-ingest>=0.2.1"

# MCP server package
python -m pip install "vera-mcp>=0.2.1"
```

## Install from source

Contributors can clone the repository and install workspace packages:

```bash
git clone https://github.com/dkylewillis/vera.git
cd vera
python -m pip install ./packages/vera-doc ./packages/vera-ingest ./packages/vera-cli
```

Or with `uv`:

```bash
uv sync --extra dev
uv run python -m vera_cli --help
```

## Convert a PDF

```bash
vera convert "manual.pdf" "manual.vera"
```

The default `hashing` embedding model is local and has no machine-learning
dependency. The resulting archive contains parsed pages, chunks, embeddings,
the keyword index, citation metadata, figures, and the original PDF.

If the output path is omitted, VERA uses the input filename with a `.vera`
suffix:

```bash
vera convert "manual.pdf"
```

VERA validates the completed archive before publishing it. Image-based pages
with little or no native text are OCR-processed locally by default. English
language data is bundled, so default OCR works offline without another
installation. Selecting another language with `--ocr-language` requires its
Tesseract data. Use `--ocr off` to disable recognition or `--ocr force` to
process every page. A failed conversion does not replace an existing
destination.

## Inspect and validate

Inspect the archive:

```bash
vera inspect "manual.vera"
```

Validate integrity:

```bash
vera validate "manual.vera"
```

Both commands accept `--json` for machine-readable output.

## Search with citations

```bash
vera search "manual.vera" "stormwater detention requirements" --top-k 5 --json
```

Each result includes page range and heading path for grounded citations. Add
`--figures`, `--regions`, or `--context-chunks 1` when you need visual or
neighboring context.

## Next steps

- [CLI recipes](examples.md)
- [Convert documents](conversion.md)
- [Search documents](searching.md)
- [Document libraries](document-libraries.md)
- [Python API](python-api.md)
- [MCP integration](mcp.md)
