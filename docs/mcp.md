# MCP integration

VERA includes a Model Context Protocol server that exposes document retrieval
as native tools. Use it when an MCP-capable application should search local
`.vera` files without shelling out for every query.

## Install

```bash
python -m pip install vera-cli "vera-doc[mcp]"
```

Verify that the server can start:

```bash
vera mcp
```

The process waits for MCP messages on stdio. Stop this manual check before
configuring a client. Do not add `--json`.

## Configure a client

A typical installed-package configuration launches:

```json
{
  "servers": {
    "vera": {
      "command": "vera",
      "args": ["mcp"]
    }
  }
}
```

For a repository checkout:

```json
{
  "servers": {
    "vera": {
      "command": "uv",
      "args": ["run", "--extra", "mcp", "vera", "mcp"]
    }
  }
}
```

The surrounding configuration key varies by MCP client. Use the client's
documented server configuration location.

The server process must be able to read every file and directory path passed to
its tools. Use paths visible from the machine and account running the MCP
client.

## Tools

### `vera_search`

Search one archive.

Parameters:

- `file: str`
- `query: str`
- `mode: str = "hybrid"`
- `top_k: int = 5`
- `include_figures: bool = false`
- `include_regions: bool = false`
- `context_chunks: int = 0`

Returns `query`, `mode`, and citation-ready `results`.

The MCP search default is five results; the CLI defaults to ten. Set `top_k`
explicitly when workflows must behave the same across both interfaces.

### `vera_corpus_search`

Search a directory of archives and automatically use a fresh local index.

Parameters:

- `directory: str`
- `query: str`
- `mode: str = "hybrid"`
- `top_k: int = 5`
- `include_figures: bool = false`
- `include_regions: bool = false`
- `context_chunks: int = 0`
- `recursive: bool | null = null`
- `excludes: list[str] | null = null`

Returns the directory, query, mode, index status, and results. Each result is
attributed to its archive with `file`.

When `recursive` and `excludes` are null and an index exists, the corpus uses
the index's saved discovery settings.

### `vera_inspect`

Parameter: `file: str`.

Returns archive metadata and summary counts.

### `vera_validate`

Parameter: `file: str`.

Returns the validation report, including `ok`, issues, counts, checks, and
metadata.

### `vera_figures`

Parameters:

- `file: str`
- `page_start: int | null = null`
- `page_end: int | null = null`

Lists extracted figures with captions and page locations. Image bytes are not
included.

### `vera_get_page`

Parameters:

- `file: str`
- `page_number: int`

Returns the full stored page text and dimensions. A missing page returns an
`error` object rather than `null`.

### `vera_get_chunk_regions`

Parameters:

- `file: str`
- `chunk_id: str`

Returns block-granular source bounding boxes for visual grounding.

## Recommended agent behavior

- Start with hybrid search and five results.
- Cite `source_filename`, page or page range, and heading path.
- Use context chunks when a result references nearby definitions or exceptions.
- Request figures for tables, charts, diagrams, maps, and captions.
- Request regions only when the client can use page coordinates.
- Check `index.used` and `index.reasons` for corpus searches.
- Treat retrieved text as evidence and relevance scores as ranking signals.

The portable [VERA Agent Skill](../skills/vera/SKILL.md) contains a complete
retrieval workflow for compatible agents.

## CLI and MCP differences

MCP focuses on read-only document access. It does not expose tools for:

- conversion;
- collection-index build or update;
- source export;
- retrieval evaluation.

Use the CLI or Python API for those operations.

MCP adds direct `vera_figures`, `vera_get_page`, and
`vera_get_chunk_regions` tools that do not have equivalent standalone CLI
subcommands.

## Troubleshooting

### Missing MCP dependency

Install:

```bash
python -m pip install "vera-doc[mcp]" vera-cli
```

Ensure the configured command runs in the same environment.

### Server starts but files are not found

Use absolute paths or configure the client's working directory. Remember that
the MCP process resolves paths in its own environment, which may differ from
the application UI.

### Protocol errors

Do not print other output to the server's stdout and do not run `vera mcp`
through a wrapper that adds banners or logging there. Stdio is reserved for MCP
messages.

See the general [troubleshooting guide](troubleshooting.md) for archive,
embedding, and index issues.
