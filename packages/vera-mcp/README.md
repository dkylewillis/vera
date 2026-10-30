# vera-mcp

`vera-mcp` is the Model Context Protocol adapter for VERA archives and
libraries. It depends on `vera-doc` for search/storage and `vera-ingest` for
viewer helpers (pages, figures, regions). It exposes those capabilities as MCP
tools without owning retrieval implementation.

## Install

```bash
python -m pip install "vera-mcp>=0.3.0"
# or
python -m pip install "vera[mcp]>=0.3.0"
```

See the [vera-mcp documentation](https://dkylewillis.github.io/vera/packages/vera-mcp/)
for installation, client setup, tool contracts, and API reference.

See the [MCP guide](https://github.com/dkylewillis/vera/blob/main/docs/mcp.md).

Source viewer: `vera_show_sources` adds an **Open VERA sources** button beside
a normally rendered answer. The user selects `[C#]` references inside the
viewer; `vera_source_page` loads the highlighted passage. See the
[plugin source viewer](https://github.com/dkylewillis/vera/blob/main/docs/plugin.md) for source-install requirements and preview limits.
