# vera-cli

`vera-cli` publishes the `vera` console command and the `vera_cli` Python
package. It depends on `vera-doc`, `vera-ingest`, and `vera-ingest-pymupdf`,
and owns argument parsing, human and JSON output, exit codes, and retrieval
evaluation. The optional `docling` extra installs `vera-ingest-docling` for
`--parser docling`.

Use the CLI for complete document workflows rather than assembling the Python
packages directly.

## Install

From PyPI:

```bash
python -m pip install "vera-cli>=0.3.0"
python -m pip install "vera-cli[docling]>=0.3.0"
```

From a repository checkout:

```bash
python -m pip install \
  ./packages/vera-doc \
  ./packages/vera-ingest \
  ./packages/vera-ingest-pymupdf \
  ./packages/vera-cli
```

Verify the entry point:

```bash
vera --help
```

## Start here

```bash
vera convert "manual.pdf" "manual.vera"
vera validate "manual.vera"
vera search "manual.vera" "detention requirements" --top-k 5 --json
vera figures "manual.vera" --out-dir "./figures" --json
```

All one-shot commands support `--json`. `vera mcp` is a long-running stdio
server and is the exception.

## Documentation

- [Getting started](../getting-started.md) — first conversion and cited search.
- [CLI recipes](../examples.md) — conversion, search, libraries, export, and evaluation.
- [Evaluate retrieval quality](../evaluation.md).
- [Troubleshooting](../troubleshooting.md).

## Reference

- [CLI command reference](../cli-reference.md) — commands and options.
- [`vera_cli` Python reference](../reference/vera-cli.md) — exported parser and
  evaluation functions.
- [Agent CLI contract](https://github.com/dkylewillis/vera/blob/main/skills/vera/references/cli-reference.md)
  — exhaustive JSON shapes, exit codes, and filesystem effects.
