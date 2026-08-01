# vera_mcp package

Model Context Protocol server exposing VERA search and inspection tools to AI
agents.

Install with the MCP extra:

```bash
python -m pip install "vera-cli[mcp]>=0.2.1"
# or
python -m pip install "vera-mcp>=0.2.1"
```

Run the server:

```bash
vera mcp
# or
vera-mcp
```

::: vera_mcp
    options:
      members:
        - build_server
        - main
      heading_level: 2
      show_if_no_docstring: true

See [MCP integration](../mcp.md) for client configuration examples.
