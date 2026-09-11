# vera

`vera` provides the `vera` command-line interface over `vera-doc`,
`vera-ingest`, `vera-ingest-pymupdf`, and `vera-embed-openai`. It owns command parsing, text and
JSON output, exit codes, and retrieval evaluation. The Python import remains
`vera_cli`.

`vera convert` accepts repeatable `--pipeline-option KEY=VALUE` flags for
provider-owned ingest settings. Legacy flags such as `--chunk-size`,
`--overlap`, `--ocr`, `--ocr-language`, and `--ocr-dpi` remain compatibility
aliases for pipelines that accept them (`--ocr-language`/`--ocr-dpi` are
Tesseract/PyMuPDF); explicit `--pipeline-option` values win for the same key.

## Install

```bash
python -m pip install "vera>=0.3.1"
```

Install the `mcp` extra to enable `vera mcp`, or the `docling` extra for
Docling PDF layout conversion and search-only DOCX/PPTX/XLSX/HTML ingest:

```bash
python -m pip install "vera[mcp]>=0.3.1"
python -m pip install "vera[docling]>=0.3.1"
```

`pip install vera-cli` remains a compatibility alias that depends on `vera`.

See the [vera CLI documentation](https://dkylewillis.github.io/vera/packages/vera-cli/)
for installation, recipes, evaluation, and command reference.

See the [CLI reference](https://github.com/dkylewillis/vera/blob/main/docs/cli-reference.md).
