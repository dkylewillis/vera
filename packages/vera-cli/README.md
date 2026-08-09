# vera-cli

`vera-cli` provides the `vera` command-line interface over `vera-doc` and
`vera-ingest`. It owns command parsing, text and JSON output, exit codes, and
retrieval evaluation.

`vera convert` accepts repeatable `--pipeline-option KEY=VALUE` flags for
provider-owned ingest settings. Legacy flags such as `--chunk-size`,
`--overlap`, `--ocr`, `--ocr-language`, and `--ocr-dpi` remain compatibility
aliases; explicit `--pipeline-option` values win for the same key.

## Install

```bash
python -m pip install "vera-cli>=0.2.4"
```

Install the `mcp` extra to enable `vera mcp`:

```bash
python -m pip install "vera-cli[mcp]>=0.2.4"
```

See the [vera-cli documentation](https://dkylewillis.github.io/vera/packages/vera-cli/)
for installation, recipes, evaluation, and command reference.

See the [CLI reference](https://github.com/dkylewillis/vera/blob/main/docs/cli-reference.md).
