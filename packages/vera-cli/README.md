# vera-cli

`vera-cli` provides the `vera` command-line interface over `vera-doc`,
`vera-ingest`, `vera-ingest-pymupdf`, and `vera-embed-openai`. It owns command parsing, text and
JSON output, exit codes, and retrieval evaluation.

`vera convert` accepts repeatable `--pipeline-option KEY=VALUE` flags for
provider-owned ingest settings. Legacy flags such as `--chunk-size`,
`--overlap`, `--ocr`, `--ocr-language`, and `--ocr-dpi` remain compatibility
aliases for pipelines that accept them (`--ocr-language`/`--ocr-dpi` are
Tesseract/PyMuPDF); explicit `--pipeline-option` values win for the same key.

## Install

```bash
python -m pip install "vera-cli>=0.3.0"
```

Install the `mcp` extra to enable `vera mcp`, or the `docling` extra for
Advanced layout conversion:

```bash
python -m pip install "vera-cli[mcp]>=0.3.0"
python -m pip install "vera-cli[docling]>=0.3.0"
```

See the [vera-cli documentation](https://dkylewillis.github.io/vera/packages/vera-cli/)
for installation, recipes, evaluation, and command reference.

See the [CLI reference](https://github.com/dkylewillis/vera/blob/main/docs/cli-reference.md).
