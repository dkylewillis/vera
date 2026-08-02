# VERA

**Vector-Embedded Retrieval Archive** — a portable approach to document retrieval.

A `.vera` file is a self-contained SQLite archive with ready-made text chunks,
pre-computed embeddings, a keyword index, JSON metadata, and optional opaque
attachments. Move it, share it, or search it locally without a retrieval
service.

## What VERA does

VERA packages source documents into searchable archives and returns
**citation-ready results** — every hit includes its source filename, page range,
and heading path. Hybrid search fuses semantic and keyword retrieval so you can
find both exact identifiers and paraphrased questions.

Major capabilities:

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

Install the CLI from PyPI:

```bash
python -m pip install "vera-cli>=0.2.2"
```

That pulls in `vera-doc` and `vera-ingest`. Library-only installs:

```bash
python -m pip install "vera-doc>=0.2.2"
python -m pip install "vera-ingest>=0.2.2"
```

`vera-ingest` may not yet be published to PyPI. If the install fails because the
package cannot be found, install from a repository checkout instead
(`python -m pip install ./packages/vera-doc ./packages/vera-ingest`).

Contributors using [uv](https://docs.astral.sh/uv/) can clone the repository and
synchronize the workspace:

```bash
git clone https://github.com/dkylewillis/vera.git
cd vera
uv sync --extra dev --extra ml
```

## Quick example

Convert a PDF and search it from the CLI:

```bash
vera convert manual.pdf manual.vera
vera search manual.vera "stormwater detention requirements" --top-k 5 --json
```

Or create and search a database from Python:

```python
from vera import ChunkRecord, VeraDocument

with VeraDocument.create("knowledge.vera") as document:
    document.add([
        ChunkRecord(
            id="chunk-1",
            text="The minimum pipe diameter is 12 inches.",
            metadata={"source_filename": "manual.pdf", "page_start": 42},
        )
    ])

with VeraDocument.open("knowledge.vera") as document:
    for result in document.search(text="minimum pipe size", top_k=5):
        print(result.score, result.record.text)
```

## Choose a package

- [**vera-doc**](packages/vera-doc.md) — create, store, and search `.vera`
  archives from Python.
- [**vera-ingest**](packages/vera-ingest.md) — parse PDFs, run selective OCR,
  and convert sources into archives.
- [**vera-cli**](packages/vera-cli.md) — run complete workflows from the
  `vera` command.
- [**vera-mcp**](packages/vera-mcp.md) — expose retrieval to MCP-capable
  applications and agents.
- [**vera-app**](packages/vera-app.md) — install or develop the desktop
  application.

See [Choose a package](packages/index.md) for package dependencies and
responsibility boundaries, or browse the [API reference](reference/index.md).

For the desktop app, see [Run the desktop app](desktop-app-getting-started.md).
For AI agents, see [MCP integration](mcp.md) and the
[Agent Skill on GitHub](https://github.com/dkylewillis/vera/blob/main/skills/vera/SKILL.md).
