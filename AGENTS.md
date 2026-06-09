# Using SDX as an AI agent

This file teaches AI coding agents how to use SDX to retrieve context from documents.

## What is an `.sdx` file?

A single SQLite file containing a document's full text, structure (pages, headings,
figures), and pre-computed embeddings. You can search it instantly — no parsing, no
chunking, no embedding API calls, no vector database. See
[docs/sdx-spec-v0.1.md](docs/sdx-spec-v0.1.md) for the format specification.

## Quick reference

All commands support `--json` for machine-readable output on stdout.

```bash
# Search a document (hybrid = semantic + keyword, best default)
sdx search manual.sdx "stormwater detention requirements" --top-k 5 --json

# Include figure/table metadata near each result
sdx search manual.sdx "pipe sizing chart" --json --figures

# Keyword-only or semantic-only search
sdx search manual.sdx "section 4.2" --mode keyword --json
sdx search manual.sdx "how big should the pond be" --mode semantic --json

# What's in this file?
sdx inspect manual.sdx --json

# Is this file well-formed? (exit code 0 = valid, 1 = invalid)
sdx validate manual.sdx --json

# Create an .sdx from a PDF
sdx convert manual.pdf manual.sdx
```

### Search result shape (`--json`)

```json
{
  "file": "manual.sdx",
  "query": "stormwater detention requirements",
  "mode": "hybrid",
  "results": [
    {
      "rank": 1,
      "chunk_id": "chunk_0042",
      "score": 0.91,
      "page_start": 117,
      "page_end": 118,
      "heading_path": "Chapter 4 > 4.2 Detention Design",
      "text": "..."
    }
  ]
}
```

## Rules for agents

1. **Always cite sources.** Every result includes `page_start`/`page_end` and
   `heading_path`. Quote them when answering from a document, e.g.
   *"(p. 117, Chapter 4 > 4.2 Detention Design)"*.
2. **Prefer `--mode hybrid`** (the default). Use `keyword` only for exact phrases,
   IDs, or section numbers; use `semantic` for paraphrased natural-language questions.
3. **Use `--figures`** when the question involves tables, charts, diagrams, or maps —
   results gain a `figures` array with captions and page locations.
4. **Check exit codes.** `validate` returns non-zero for invalid files; `search` on a
   missing file returns non-zero. Parse stdout as JSON only when exit code is 0.
5. **Don't read the SQLite file directly** unless the CLI is unavailable — the schema
   is documented in the spec, but the CLI/MCP tools are the stable interface.

## MCP server

SDX ships an MCP server (stdio) exposing the same capabilities as tools:

| Tool | Purpose |
|------|---------|
| `sdx_search` | Hybrid/semantic/keyword search with optional figure metadata |
| `sdx_inspect` | Document metadata, page/chunk counts, embedding model |
| `sdx_validate` | Integrity check |
| `sdx_figures` | List figures/images with captions, optionally by page range |
| `sdx_get_page` | Full text of a specific page |

Requires the `mcp` extra: `pip install sdx[mcp]`. Example VS Code config
(`.vscode/mcp.json`):

```json
{
  "servers": {
    "sdx": {
      "command": "uv",
      "args": ["run", "--extra", "mcp", "sdx", "mcp"]
    }
  }
}
```

## Working on this repository

- Python 3.10+, dependencies managed with [uv](https://docs.astral.sh/uv/):
  `uv sync --extra dev --extra ml --extra workbench --extra mcp`
- Run tests with `pytest` (all tests must pass before committing).
- Core code lives in [src/sdx](src/sdx); the format spec is
  [docs/sdx-spec-v0.1.md](docs/sdx-spec-v0.1.md) — keep code and spec in sync.
- Retrieval quality is tracked with `sdx eval` against the query sets in
  [examples](examples); don't regress the baselines in the README.
