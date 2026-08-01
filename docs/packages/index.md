# Choose a package

VERA is one project composed of independently installable packages. Start with
the package that owns the capability you need.

| Package | Install name | Import or command | Use it for |
|---------|--------------|-------------------|------------|
| [vera-doc](vera-doc.md) | `vera-doc` | `import vera` | Creating, storing, and searching `.vera` archives |
| [vera-ingest](vera-ingest.md) | `vera-ingest` | `import vera_ingest` | PDF parsing, OCR, chunking, and conversion |
| [vera-cli](vera-cli.md) | `vera-cli` | `vera` / `import vera_cli` | Shell workflows and retrieval evaluation |
| [vera-mcp](vera-mcp.md) | `vera-mcp` | `vera mcp` / `import vera_mcp` | Exposing VERA retrieval to MCP clients |
| [vera-app](vera-app.md) | `vera-app` | Desktop application | Interactive conversion, search, and grounded answers |

## Dependency direction

```text
vera-ingest ─┐
vera-cli ─────┼──> vera-doc
vera-app ─────┤
vera-mcp ─────┘
```

`vera-doc` is the storage and retrieval foundation. The other packages compose
it without moving their own responsibilities into the core library.

## Documentation model

Each package section contains the documentation appropriate for its public
surface:

- Python libraries include API reference generated from source docstrings.
- The CLI emphasizes commands, output contracts, and recipes.
- MCP emphasizes client configuration and tool contracts.
- The desktop app emphasizes installation and user workflows rather than
  treating its private sidecar modules as a supported public API.

Shared format specifications and contributor architecture remain outside the
package sections because they describe the repository and `.vera` format as a
whole.
