# VERA - Vector-Embedded Retrieval Archive

[![Latest release](https://img.shields.io/github/v/release/dkylewillis/vera)](https://github.com/dkylewillis/vera/releases/latest)
[![PyPI - vera-doc](https://img.shields.io/pypi/v/vera-doc?label=vera-doc)](https://pypi.org/project/vera-doc/)
[![License](https://img.shields.io/github/license/dkylewillis/vera)](LICENSE)


A `.vera` file is a portable embedded vector database: a self-contained SQLite file containing
ready-made text chunks, embeddings, a keyword index, JSON metadata, and
optional opaque attachments. Move it, share it, or search it locally without a
retrieval service.

The unique core is [`vera-doc`](https://pypi.org/project/vera-doc/) — an
embeddable Python library that stores and searches `.vera` archives. The VERA
desktop app is a polished product built on that same foundation. The CLI and
MCP server give AI agents and applications the same citation-ready retrieval
layer.

[Download VERA for Windows](https://github.com/dkylewillis/vera/releases/latest)
· [`pip install vera-doc`](#build-on-vera) to embed it
· [Read the documentation](https://dkylewillis.github.io/vera/)

<img src="docs/assets/readme/hero-grounded-answer.png" alt="VERA desktop app showing an Ask answer beside the source PDF with a cited passage highlighted" width="85%">


<!-- TODO(assets): 20–30s feature tour video — upload to a GitHub Release or
external host, then add: [Watch the feature tour](https://github.com/dkylewillis/vera/releases/latest) -->

## Try it in five minutes

Converting and searching documents is fully local and needs no account or API
key. You only connect a model provider when you want AI answers.

1. **Install VERA.** Download the `VERA Setup` installer from the
   [latest Windows release](https://github.com/dkylewillis/vera/releases/latest)
   and run it.
2. **Convert your documents.**
   - **One or more PDFs** — in **Convert PDF** → **Individual PDFs**, use
     **Choose PDFs**, or select files in Explorer and right-click
     **Convert PDF**. VERA writes a portable `.vera` archive beside
     each file. To rebuild an archive with a different parser or embedding,
     right-click the `.vera` file and choose **Reconvert…**.
   - **Entire library** — right-click the folder in Explorer and choose
     **Convert PDFs…**, or use **Convert PDF** → **PDF Directory**. Then use
     **File > Open Folder** to activate it. On your first
     Search or Ask, VERA shows **Build library index?** — select
     **Build index** to make the library fast. The footer reports completed
     files, total files, the current archive, and indexed chunks as it runs.
3. **Connect a model.** Go to **File > LLM Providers**, select a provider,
   paste your **API Key**, select **Save Key**, then **Save & Close**. Keys
   are stored encrypted on your machine. Local **Ollama** and **LM Studio**
   servers work too — no key needed.
4. **Search.** Open **Search** and query your documents. Hybrid retrieval
   (semantic + keyword) works entirely offline.
5. **Ask and verify.** Ask a question, then select a citation to see the
   highlighted supporting text in the source document.

The desktop app converts with local hashing embeddings; the model provider is
only used for Ask responses. Use the CLI when you need a Sentence Transformers
embedding model or explicit OCR control. For the complete walkthrough and
troubleshooting, see [Run the desktop app](docs/desktop-app-getting-started.md).
Long library inspections report per-archive progress in the same footer used
for conversion and indexing.

## How it works

During conversion, the default `vera-ingest-pymupdf` pipeline extracts native
PDF text, selectively OCRs image-based pages, and preserves headings, figures,
and page coordinates. `vera-doc` then stores the chunks, embeddings, and
keyword index in one validated `.vera` file. The desktop app, CLI, and MCP
server all search that same archive:

<img src="convert.png" alt="VERA conversion workflow from PDF parsing and OCR through chunking, embedding, and keyword indexing into a portable .vera archive" width="60%">

At search time, hybrid retrieval in `vera-doc` fuses semantic and keyword
rankings and returns chunks with their source file, page range, and heading
path — grounded context for a person or an LLM, with no retrieval service
required:

<img src="search.png" alt="VERA hybrid search workflow combining semantic and keyword search to provide cited context for an LLM response" width="60%">

On a 1,038-page stormwater manual (2,442 chunks), hybrid search hits 9/10
real-world regulatory queries at MRR 0.900 — tracked continuously with
[`vera eval`](docs/evaluation.md).

## What’s unique: how VERA is built

The distinctive idea is the portable `.vera` archive and the `vera-doc`
engine that reads and writes it. The desktop app is a flagship product built
on that same stack — not the definition of VERA.

| Package | Role |
|---------|------|
| [`vera-doc`](https://pypi.org/project/vera-doc/) | Embeddable storage and search (`import vera`) |
| [`vera-ingest`](https://pypi.org/project/vera-ingest/) | Conversion registry, shared types, and archive writer |
| [`vera-ingest-pymupdf`](https://pypi.org/project/vera-ingest-pymupdf/) | Default PDF extraction / OCR pipeline (pulled in by CLI/app) |
| [`vera-cli`](https://pypi.org/project/vera-cli/) / [`vera-mcp`](https://pypi.org/project/vera-mcp/) | Shell and agent frontends |
| `vera-app` | Desktop product — a full implementation of the stack |

```text
vera-ingest-pymupdf ─┐
vera-ingest ─────────┼──> vera-doc
vera-cli ────────────┤
vera-app ────────────┤
vera-mcp ────────────┘
```

**Who installs what**

- End users → the [desktop app](https://github.com/dkylewillis/vera/releases/latest)
- Other apps with ready-made chunks → `vera-doc` only
- PDF pipelines → `vera-doc` + `vera-ingest` + `vera-ingest-pymupdf`
- Agents and scripts → CLI / MCP

See [Contributing and architecture](docs/architecture.md) and the
[package overview](packages/README.md) for boundaries and dependency rules.

## What VERA gives you

- **Portable document archives** — each `.vera` file is self-contained;
  copy it anywhere and it stays searchable.
- **Grounded answers** — follow citations to the page, heading, and
  highlighted source text.
- **Libraries that stay fast** — a persistent local index makes searching
  hundreds or even thousands of documents possible; update it as documents
  change.
- **Source-first review** — inspect pages and figures, validate archives, and
  export the original PDF back out at any time. The desktop app keeps figure
  search results lightweight and loads image previews only for the selected
  result.

<!-- TODO(assets): uncomment when captured — see docs/assets/readme/README.md
<img src="docs/assets/readme/convert-single-pdf.png" alt="Convert PDF view converting a single PDF into a .vera archive" width="45%">
<img src="docs/assets/readme/provider-setup.png" alt="LLM Providers dialog with a provider, API key field, and enabled models" width="45%"> -->

## Build on VERA

### Use VERA as a library

Applications with ready-made chunks can use `vera-doc` directly without
installing PDF/OCR dependencies:

```bash
python -m pip install "vera-doc>=0.2.4"
```

```python
from vera import ChunkRecord, VeraDocument

with VeraDocument.create("knowledge.vera") as document:
    document.add([
        ChunkRecord(
            id="chunk-1",
            text="The minimum pipe diameter is 12 inches.",
            metadata={"source": "manual.pdf", "page": 42},
        )
    ])

with VeraDocument.open("knowledge.vera") as document:
    results = document.search(text="minimum pipe size", top_k=5)
```

Archives record whether stored embeddings are L2-normalized, unnormalized, or
unknown. Custom vector pipelines can set `embedding_normalization` at creation;
`vera-doc` validates vectors when the archive declares L2 normalization.

### Convert sources

PDF extraction lives in `vera-ingest-pymupdf` (pulled in by `vera-cli`) and is
composed through the `vera-ingest` registry by `vera convert`:

```bash
python -m pip install "vera-cli>=0.2.4"
```

```bash
# Convert a PDF to a portable retrieval archive.
vera convert input.pdf output.vera

# Provider-owned ingest options (repeatable; overrides legacy aliases).
vera convert input.pdf --pipeline-option chunk_size=700 --pipeline-option ocr_mode=auto

# Build a persistent local index for a document library.
vera index build ./library --recursive

# Return grounded results for an application or agent.
vera search ./library "What are the detention requirements?" --top-k 5 --json
```

### CLI, MCP, and Agent Skill

The default hybrid search combines semantic and keyword retrieval. Every result
includes its source filename, page range, and heading path. Add
`--context-chunks`, `--figures`, or `--regions` when the agent needs nearby
text, figure metadata, or page coordinates.

- [CLI quick start and recipes](docs/getting-started.md)
- [CLI reference](docs/cli-reference.md)
- [Connect an MCP client](docs/mcp.md)
- [Install the VERA Agent Skill](docs/agent-skills.md)
- [Use the Python API](docs/python-api.md)
- [Agent quick reference](AGENTS.md)
- [VERA Agent Skill package (SKILL.md)](skills/vera/SKILL.md)
- [VERA Agent Skill CLI reference](skills/vera/references/cli-reference.md)

## Documentation

Preview the documentation locally with:

```bash
uv run --extra docs mkdocs serve
```

- [Desktop app guide](docs/desktop-app-getting-started.md)
- [Convert documents](docs/conversion.md)
- [Search documents](docs/searching.md)
- [Search and index document libraries](docs/document-libraries.md)
- [Work with figures and highlight regions](docs/figures-and-regions.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Current VERA 0.2 format specification](docs/vera-spec-v0.2.md)
- [Legacy VERA 0.1 format specification](docs/vera-spec-v0.1.md)
- [Contributing and architecture](docs/architecture.md)
- [Project roadmap](ROADMAP.md)

## Status and support

VERA is an experimental pre-1.0 project. The desktop installer is available from
[GitHub Releases](https://github.com/dkylewillis/vera/releases) and currently
targets Windows. The `.vera` schema and format may change before a stable
release.

VERA is licensed under [Apache-2.0](LICENSE).
