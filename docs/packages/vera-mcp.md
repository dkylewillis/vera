# vera-mcp

`vera-mcp` publishes the `vera_mcp` Python package and `vera-mcp` entry point.
It depends on `vera-doc` for storage/search and `vera-ingest` for viewer helpers
(pages, figures, regions, source export). It exposes archive and corpus
retrieval as Model Context Protocol tools.

`vera_search` and `vera_corpus_search` accept `pretty: true` to add readable,
citation-ready `context` while retaining their structured result arrays.

The package is a protocol adapter. Ranking, validation, and conversion remain
implemented by `vera-doc` and `vera-ingest`.

## Install

From PyPI:

```bash
python -m pip install "vera[mcp]>=0.3.0"
```

Or install the package directly:

```bash
python -m pip install "vera-mcp>=0.3.0"
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
  figures, figure image fetch, pages, chunk fetch, and regions.
- [Recommended agent behavior](../mcp.md#recommended-agent-behavior).
- [Portable Agent Skill](../agent-skills.md).
- [MCP troubleshooting](../mcp.md#troubleshooting).

## API reference

- [`vera_mcp`](../reference/vera-mcp.md) — `build_server()` and the stdio entry point.

MCP intentionally does not expose conversion, index mutation, source export, or
retrieval evaluation. Use `vera` or the Python packages for those tasks.

Desktop ChatGPT Bridge is a separate fail-closed entry (`vera-mcp-bridge` /
`vera-sidecar mcp-bridge`) that requires `VERA_BRIDGE_POLICY_PATH` and omits
`vera_validate`. Ordinary `vera mcp` stays unrestricted. See
[desktop-bridge-poc.md](../desktop-bridge-poc.md).

Source viewer: `vera_show_sources` adds an **Open VERA sources** button beside
a normally rendered answer. The user selects `[C#]` references inside the
viewer; `vera_source_page` loads the highlighted passage. See the
[plugin source viewer](https://github.com/dkylewillis/vera/blob/main/docs/plugin.md) for source-install requirements and preview limits.
