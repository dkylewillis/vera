# VERA

**Vector-Embedded Retrieval Archive** — a portable approach to document retrieval.

A `.vera` file is a self-contained SQLite archive with ready-made text chunks,
pre-computed embeddings, a keyword index, JSON metadata, and optional opaque
attachments. Move it, share it, or search it locally without a retrieval
service.

VERA packages source documents into searchable archives and returns
**citation-ready results** — every hit includes its source filename, page range,
and heading path. Hybrid search fuses semantic and keyword retrieval so you can
find both exact identifiers and paraphrased questions.

## Getting started

Ready to try VERA? Start here:

<div class="grid cards" markdown>

-   :material-download: **Getting started**

    ---

    Install VERA, convert a PDF, and run your first cited search.

    [:octicons-arrow-right-24: Getting started](getting-started.md)

-   :material-book-open-variant: **Concepts**

    ---

    Learn how `.vera` archives, chunks, and library indexes work.

    [:octicons-arrow-right-24: Concepts](concepts/index.md)

-   :material-code-braces: **Examples**

    ---

    Copyable CLI recipes and Python examples for common workflows.

    [:octicons-arrow-right-24: Examples](examples/index.md)

-   :material-connection: **Integrations**

    ---

    Connect MCP clients, agent skills, and the desktop app.

    [:octicons-arrow-right-24: MCP server](mcp.md)

-   :material-api: **Reference**

    ---

    Generated Python API docs and the CLI reference.

    [:octicons-arrow-right-24: Database API](reference/database.md)

</div>

## Features

- **Portable archives** — each `.vera` file is self-contained and searchable
  anywhere.
- **Hybrid retrieval** — semantic, keyword, and fused hybrid search modes.
- **Grounded citations** — page numbers, heading paths, figures, and highlight
  regions for visual grounding.
- **Document libraries** — persistent local indexes make searching hundreds of
  archives fast.
- **CLI, Python API, and MCP** — the same retrieval layer for applications,
  scripts, and AI agents.

## Install

VERA is currently installed from source. Clone the repository and install the
workspace packages:

```bash
git clone https://github.com/dkylewillis/vera.git
cd vera
python -m pip install ./packages/vera-doc ./packages/vera-cli
```

Contributors using [uv](https://docs.astral.sh/uv/) can synchronize the full
workspace:

```bash
uv sync --extra dev --extra ml
```

## Quick example

```bash
vera convert manual.pdf manual.vera
vera search manual.vera "stormwater detention requirements" --top-k 5 --json
```

```python
from vera import ChunkRecord, VeraDatabase

with VeraDatabase.create("knowledge.vera") as database:
    database.add([
        ChunkRecord(
            id="chunk-1",
            text="The minimum pipe diameter is 12 inches.",
            metadata={"source_filename": "manual.pdf", "page_start": 42},
        )
    ])

with VeraDatabase.open("knowledge.vera") as database:
    for result in database.search(text="minimum pipe size", top_k=5):
        print(result.score, result.record.text)
```

For the desktop app, see [Run the desktop app](desktop-app-getting-started.md).
For AI agents, see the
[Agent Skill on GitHub](https://github.com/dkylewillis/vera/blob/main/skills/vera/SKILL.md).
