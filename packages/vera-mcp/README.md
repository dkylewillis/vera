# vera-mcp

`vera-mcp` is the Model Context Protocol adapter for VERA archives and
libraries. It depends on `vera-doc` for search/storage and `vera-ingest` for
viewer helpers (pages, figures, regions). It exposes those capabilities as MCP
tools without owning retrieval implementation.

## Install

```bash
python -m pip install "vera-mcp>=0.2.1"
# or
python -m pip install "vera-cli[mcp]>=0.2.1"
```

See the [vera-mcp documentation](https://dkylewillis.github.io/vera/packages/vera-mcp/)
for installation, client setup, tool contracts, and API reference.

See the [MCP guide](https://github.com/dkylewillis/vera/blob/main/docs/mcp.md).
