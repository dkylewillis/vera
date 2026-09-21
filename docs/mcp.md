# MCP integration

The [VERA plugin](plugin.md) bundles this server with the portable agent skill
and launches `vera-mcp` over stdio for search, read, and refine workflows.

VERA includes a Model Context Protocol server that exposes document retrieval
as native tools. Use it when an MCP-capable application should search local
`.vera` files without shelling out for every query.

## Install

```bash
python -m pip install "vera[mcp]>=0.3.0"
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

### `vera_library_info`

Returns the approved library root and search bounds when running under Desktop
bridge policy. Unrestricted local MCP returns `unrestricted: true` and no grant.

### Compact search output

Both search tools accept `output: "compact" | "full"` (default `"full"` for
compatibility). Prefer compact output for document questions:

```json
{"file": "/library/report.vera", "query": "capacity expansion", "top_k": 5, "output": "compact"}
```

Compact output contains `results` with complete passage `text`, `chunk_id`,
absolute `file`, and available `source_filename`, `page_start`, `page_end`, and
`heading_path`. Requested nonempty `before_chunks` and `after_chunks` use the
same compact fields. Missing source metadata is not invented. These locators
can be passed directly to `vera_get_chunk` and `vera_show_sources`.

Corpus output includes `warnings` only when `skipped_files` or
`skipped_semantic_model_groups` is nonempty, preserving their diagnostic details.
An empty successful search has `results: []`; tool failures remain errors.
Compact mode omits scores, arbitrary metadata, and routine index diagnostics.
Use full output for those details. Combining compact output with `pretty: true`,
`include_figures: true`, or `include_regions: true` is an error; select full
output for those options. CLI `--pretty` behavior is unchanged.

### `vera_search`

Search one archive.

Parameters:

- `file: str`
- `query: str`
- `mode: str = "hybrid"`
- `top_k: int = 10`
- `include_figures: bool = false`
- `include_regions: bool = false`
- `context_chunks: int = 0`
- `where: dict[str, str | list[str]] | null = null`
- `pretty: bool = false`

Returns `query`, `mode`, and citation-ready `results`. A list value is IN;
distinct keys are AND. Filters stored metadata before `top_k`. When `pretty`
is true, the response also includes `context`, a Markdown-like rendering with
headings, source/page citations, complete text, requested neighboring chunks,
and requested figure captions. Structured results remain unchanged.

The MCP search default is ten results, matching the CLI and
`VeraDocument.search`.

### `vera_corpus_search`

Search a directory of archives and automatically use a fresh local index.

Parameters:

- `directory: str`
- `query: str`
- `mode: str = "hybrid"`
- `top_k: int = 10`
- `include_figures: bool = false`
- `include_regions: bool = false`
- `context_chunks: int = 0`
- `recursive: bool | null = null`
- `excludes: list[str] | null = null`
- `includes: list[str] | null = null`
- `where: dict[str, str | list[str]] | null = null`
- `pretty: bool = false`

Returns the directory, query, mode, index status, `skipped_files`,
`skipped_semantic_model_groups`, and results. Each result is attributed to its
archive with `file`. Malformed archives are excluded and reported with their
paths and validation reasons. For indexed semantic and hybrid searches,
`skipped_semantic_model_groups` reports any model group omitted because its
query embedder was unavailable or had the wrong dimension; hybrid keyword
matches may still be returned.

When `pretty` is true, the response also includes the same `context` field as
`vera_search`; corpus result sections include their archive paths.

When `recursive`, `excludes`, and `includes` are null and an index exists, the
corpus uses the index's saved discovery settings. `where` uses the same AND / IN
semantics as the CLI. Chunk-only metadata filters that are not in the collection
index set `index.used` to false.

### `vera_inspect`

Parameter: `file: str`.

Returns archive metadata and summary counts, including `file` (the requested
path) and `path` (the opened archive). The payload matches
`vera inspect FILE --json`: archive metadata is spread at the top level, so
the pipeline `ocr` diagnostics bag is present when convert wrote it. There is
no text-mode omit. See
[Inspect metadata](validation-and-export.md#pipeline-diagnostics-ocr).

### `vera_validate`

Parameter: `file: str`.

Returns the validation report, including `file` (requested), `path` (opened),
`ok`, issues, counts, checks, and metadata.

### `vera_figures`

Parameters:

- `file: str`
- `page_start: int | null = null`
- `page_end: int | null = null`

Lists extracted figures with captions and page locations. Image bytes are not
included. Use `vera_get_figure` to fetch one stored raster.

### `vera_get_figure`

Parameters:

- `file: str`
- `asset_id: str`

Returns native MCP image content for that figure attachment plus JSON
metadata (`caption`, `page_number`, `bbox`, `mime_type`, `asset_id`). A missing
or non-figure id returns `{"error": "..."}` rather than other attachment bytes.
The server does not write files.

### `vera_get_page`

Parameters:

- `file: str`
- `page_number: int`

Returns the full stored page text and dimensions. A missing page returns an
`error` object rather than `null`.

### `vera_get_chunk`

Parameters:

- `file: str`
- `chunk_id: str`
- `include_figures: bool = false`
- `include_regions: bool = false`

Returns one stored chunk as citation-ready JSON, matching
`vera get FILE CHUNK_ID --json` (`ok`, `file`, `path`, `chunk_id`, `text`,
and citation fields; no `score`). `ok`, `file`, and `path` name the opened
archive and are not taken from chunk metadata. A missing or whitespace-only
id returns `{"ok": false, "error": "chunk not found: ..."}` rather than
raising. This differs from `vera_get_page`, which returns `{"error": "..."}`
without `ok`.

### `vera_get_chunk_regions`

Parameters:

- `file: str`
- `chunk_id: str`

Returns block-granular source bounding boxes for visual grounding.

## Recommended agent behavior

- Start with hybrid search and five results.
- Cite `source_filename`, page or page range, and heading path.
- Reload a known `chunk_id` with `vera_get_chunk` when verifying a quote or
  when you need the stored chunk body rather than a search hit.
- Use context chunks when a result references nearby definitions or exceptions.
- Request figures for charts, diagrams, maps, and captions (`include_figures`
  or `vera_figures`). Call `vera_get_figure` with an `asset_id` when you need
  to see the stored raster. Tables are usually markdown in the chunk.
- Request regions only when the client can use page coordinates.
- Check `index.used`, `index.reasons`, and `skipped_files` for corpus searches.
- Treat retrieved text as evidence and relevance scores as ranking signals.

The portable [VERA Agent Skill](https://github.com/dkylewillis/vera/blob/main/skills/vera/SKILL.md) contains a complete
retrieval workflow for compatible agents.

## Desktop ChatGPT bridge (developer-mode PoC)

Desktop can supervise OpenAI Secure MCP Tunnel with a restricted MCP child
(`vera-sidecar mcp-bridge` / `vera-mcp-bridge`). That mode requires
`VERA_BRIDGE_POLICY_PATH` and only searches `.vera` archives under an approved
local library (`top_k` ≤ 20, `context_chunks` ≤ 2). It does not register `vera_validate`
and unsets `VERA_AUTO_INSTALL_SEMANTIC_DEPS`. Missing or
invalid policy exits 2. Ordinary `vera mcp` remains unrestricted for local IDE
use. See [desktop-bridge-poc.md](desktop-bridge-poc.md) and the
[setup runbook](desktop-bridge-poc-setup-runbook.md). In the app, open
**Settings → ChatGPT Bridge**. Its setup wizard persists a selected
`tunnel-client` path (or uses automatic detection), checks the approved library
and tunnel ID before connecting, then has `tunnel-client` choose a loopback
health port and reads the URL it reports. It records redacted tunnel diagnostics
in the local sidecar log.

## CLI and MCP differences

MCP focuses on read-only document access. It does not expose tools for:

- conversion;
- collection-index build or update;
- source export;
- retrieval evaluation.

Use the CLI or Python API for those operations.

MCP adds `vera_get_page` and `vera_get_chunk_regions`, which have no
standalone CLI subcommands. `vera_get_chunk` matches `vera get`.
`vera_figures` listing matches `vera figures`;
`vera_get_figure` is the MCP way to return image content (the CLI writes files
with `vera figures --out-dir` instead).

## Troubleshooting

### Missing MCP dependency

Install:

```bash
python -m pip install "vera[mcp]>=0.3.0"
```

That extra installs `vera-mcp` and pins the MCP Python SDK to `mcp>=1.0,<2`.
Do not `pip install mcp` by itself: SDK 2.x removed `mcp.server.fastmcp`, which
`vera mcp` still uses. Ensure the configured command runs in the same
environment.

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

Source viewer: `vera_show_sources` adds an **Open VERA sources** button beside
a normally rendered answer. The user selects `[C#]` references inside the
viewer; `vera_source_page` loads PDF pages on demand as the user scrolls from
the highlighted passage. See the
[plugin source viewer](plugin.md) for source-install requirements and preview limits.
