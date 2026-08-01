# vera-mcp

`vera-mcp` publishes the `vera_mcp` Python package and `vera-mcp` entry point.
It depends on `vera-doc` and exposes read-only archive and corpus retrieval as
Model Context Protocol tools.

The package is a protocol adapter. Storage, search, ranking, validation, and
figure access remain implemented by `vera-doc`.

## Install

```bash
python -m pip install "vera-cli[mcp]"
```

From a repository checkout:

```bash
uv run --extra mcp vera mcp
```

The server communicates over stdio. Do not add `--json` or write unrelated
output to stdout.

## Documentation

- [MCP setup and client configuration](../mcp.md#configure-a-client).
- [MCP tools](../mcp.md#tools) — search, corpus search, inspect, validate,
  figures, pages, and regions.
- [Recommended agent behavior](../mcp.md#recommended-agent-behavior).
- [Portable Agent Skill](../agent-skills.md).
- [MCP troubleshooting](../mcp.md#troubleshooting).

## API reference

- [`vera_mcp`](../reference/vera-mcp.md) — `build_server()` and the stdio entry point.

MCP intentionally does not expose conversion, index mutation, source export, or
retrieval evaluation. Use `vera-cli` or the Python packages for those tasks.
