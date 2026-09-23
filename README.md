# VERA — Vector-Embedded Retrieval Archive

[![Latest release](https://img.shields.io/github/v/release/dkylewillis/vera)](https://github.com/dkylewillis/vera/releases/latest)
[![PyPI - vera](https://img.shields.io/pypi/v/vera?label=vera)](https://pypi.org/project/vera/)
[![License](https://img.shields.io/github/license/dkylewillis/vera)](LICENSE)

**Convert once. Search anywhere.**

VERA turns documents into searchable `.vera` files. Each file holds the text,
embeddings, keyword index, citations, and original source in one SQLite archive.
Copy it, share it, or hand it to an AI agent. No database server to run.

One PDF becomes one searchable `.vera` file. A library is a folder of those
files plus an index, so you can search many archives together.

## Convert → index → search

With Python 3.10+, convert a single document. Conversion already builds its
search index. `--pretty` prints human-readable results instead of raw JSON:

```bash
python -m pip install "vera>=0.3.2"

vera convert manual.pdf
vera search manual.vera "stormwater detention" --pretty
```

A folder of PDFs or Markdown files becomes a library. Convert each file, build
one index, then search them together:

```bash
vera convert ./library --recursive
vera index build ./library --recursive
vera search ./library "stormwater detention" --pretty
```

If you stamped metadata at convert time, narrow results before ranking:

```bash
vera search ./library "stormwater detention" --where company=GRID --pretty
```

This works locally with no API key or model download. PDFs get automatic OCR
when needed; English OCR data is bundled.

A library index is optional and speeds up repeated searches. VERA uses it
automatically when fresh. After adding or replacing archives, run
`vera index update ./library`. See [document libraries](docs/document-libraries.md).

## Keyword or semantic?

| Mode | Finds | Good for |
|------|-------|----------|
| `keyword` | Words in the text, using SQLite full-text search | Names, identifiers, section numbers |
| `semantic` | Similar meanings, using embeddings | Questions phrased differently from the source |
| `hybrid` (default) | A combination of both rankings | General questions with useful keywords |

**The default embedder is `hashing`: fast, offline, and based on shared words.**
It supports all three modes, but does not learn meaning or synonyms. For
meaning-based semantic and hybrid search, convert with a neural model.

### Enable semantic search

Install the local model runtime, then choose MiniLM at conversion time:

```bash
python -m pip install "vera-doc[ml]"
vera convert manual.pdf manual-semantic.vera --model sentence-transformers:all-MiniLM-L6-v2

vera search manual-semantic.vera "how can we prevent downstream flooding?" --mode semantic --pretty
vera search manual-semantic.vera "stormwater detention" --mode keyword --pretty
vera search manual-semantic.vera "how can we prevent downstream flooding?" --pretty
```

The first conversion downloads the model. With the model cached, it can run
locally and offline. Search selects the model recorded in the archive and
embeds only your query; document embeddings are already stored.

Changing `--mode` does **not** change an archive's embeddings. To upgrade a
hashing archive, convert its source again with `--model`. For a whole library:

```bash
vera convert ./library --recursive --overwrite --model sentence-transformers:all-MiniLM-L6-v2
vera index update ./library
```

Here `--overwrite` replaces existing batch outputs; without it, unchanged
sources are skipped even when you select a different model.

Keyword search needs no embedding model. Semantic and hybrid search need the
archive's provider and model available on the machine doing the searching.
See [searching](docs/searching.md) for ranking, citations, and result details.

## Filter your search

Add metadata when converting, then use it to narrow results:

```bash
vera convert manual.pdf ./library/manual.vera --metadata project=riverpark --metadata type=manual
vera search ./library "stormwater detention" --where project=riverpark --pretty
```

Combine filters, match several values, or search selected folders:

```bash
# Both conditions must match
vera search ./library "stormwater detention" --where project=riverpark --where type=manual

# Either project may match
vera search ./library "stormwater detention" --where project=riverpark,lakeside

# Only archives under the manuals folder
vera search ./library "stormwater detention" --recursive --include "manuals/**"
```

Metadata filters apply **before** `--top-k`, so the limit counts matching
results. Run `vera index update ./library` after changing archives to refresh
the library index. More [filtering examples](docs/searching.md#filter-before-top_k).

## Choose your embeddings

Select an embedding provider with `--model provider:model-id`:

| Provider | Example | Setup |
|----------|---------|-------|
| Hashing | `hashing` | Included; lexical similarity, no downloads |
| Local neural model | `sentence-transformers:all-MiniLM-L6-v2` | Install `vera-doc[ml]`; download the model once |
| Another local model | `sentence-transformers:all-mpnet-base-v2` | Same runtime; a separate model download |
| OpenAI | `openai:text-embedding-3-small` | Included with `vera`; set `OPENAI_API_KEY` |
| Your own provider | `custom:all-MiniLM-L6-v2` | Install a Python plugin, as below |

Provider options go through `--embedder-option`:

```bash
vera convert manual.pdf manual-hashing.vera --model hashing --embedder-option dimension=256
vera convert manual.pdf manual-openai.vera --model openai:text-embedding-3-small --embedder-option batch_size=64
```

OpenAI calls a hosted API for conversion and for each semantic or hybrid
query. Anyone searching that archive needs their own `OPENAI_API_KEY`;
keyword search still works without one.

For MiniLM without Torch, VERA also supports `vera-doc[onnx]` with a
VERA-exported model snapshot. See [embedding setup](docs/conversion.md#embedding-models).

### A simple embedding plugin

A plugin supplies three things: a **model name**, a **vector dimension**, and
an **`embed(texts)` method**. This small adapter uses Sentence Transformers;
replace the embedding implementation to integrate your own runtime or service.
The built-in `sentence-transformers` provider already covers the models shown
here; this example demonstrates how to register a provider of your own.

`custom_embeddings.py`:

```python
from sentence_transformers import SentenceTransformer

DIMENSIONS = {"all-MiniLM-L6-v2": 384, "all-mpnet-base-v2": 768}


class CustomEmbedder:
    normalization = "l2"

    def __init__(self, model_id: str):
        self.model_name = f"custom:{model_id}"
        self.dimension = DIMENSIONS[model_id]
        self._model_id = model_id
        self._model = None

    def embed(self, texts: list[str]):
        if self._model is None:
            self._model = SentenceTransformer(self._model_id, device="cpu")
        return self._model.encode(texts, normalize_embeddings=True)
```

Register the class as a factory in `pyproject.toml`:

```toml
[project.entry-points."vera.embedders"]
custom = "custom_embeddings:CustomEmbedder"
```

The complete [two-file example](examples/embedding-plugin) includes the package
metadata and dependencies. From a clone of this repository, install it in the
same Python environment as VERA:

```bash
python -m pip install ./examples/embedding-plugin
vera convert manual.pdf manual-custom.vera --model custom:all-MiniLM-L6-v2
vera search manual-custom.vera "how can we prevent downstream flooding?" --mode semantic --pretty
```

VERA discovers the entry point automatically. The stored `custom:…` model name
lets a later search recreate the same embedder, so recipients also need the
plugin installed. No VERA source changes are needed.

See [creating an embedding provider](docs/creating-an-embedding-provider.md)
for options, credentials, and model discovery, or
[creating an ingest pipeline](docs/creating-an-ingest-pipeline.md) to add a parser.

## Use it with an AI agent

Add `--json` for structured results, or `--pretty` for readable text with
citations and surrounding context:

```bash
vera search manual.vera "stormwater detention" --top-k 5 --json
vera search manual.vera "stormwater detention" --context-chunks 1 --pretty
vera get manual.vera chunk_0042 --json
```

Results carry source filename, page range, and heading path. Add `--figures`
for figure metadata or `--regions` for source highlights.

- **CLI:** any agent that can run shell commands can use VERA.
- **MCP:** install `vera[mcp]` and run `vera mcp`. Search with `output: "compact"`
  for concise evidence and viewer-ready citations. [Connect a client](docs/mcp.md).
- **Agent Skill:** install the portable [VERA skill](skills/vera-search/SKILL.md), with its
  [CLI reference](skills/vera-search/references/cli-reference.md).
  [Installation guide](docs/agent-skills.md).
- **Codex plugin:** install the local [VERA plugin](docs/plugin.md) from its
  repo marketplace (`.agents/plugins/marketplace.json`) to use the
  same MCP tools and skill, plus source-viewer buttons with citation highlights.
  VERA Local runs on the Codex task host; no desktop app or tunnel is required.
  The remote ChatGPT Bridge remains a separate, optional connection.
  Before the first hybrid or semantic search it installs Sentence Transformers
  in the MCP server's Python environment; the first model use may still download
  model weights.
- **Python:** use `vera-doc` for storage and search, or `vera-ingest` for
  conversion. [Python API](docs/python-api.md).

## Prefer a desktop app?

The [Windows installer](https://github.com/dkylewillis/vera/releases/latest)
includes conversion, library search, and a PDF viewer with citation highlights.
Set it as the default app for `.vera` files to open an archive in Document
Preview by double-clicking it in Windows File Explorer or on the desktop.
Connect an LLM provider for grounded questions and answers.
For private developer-mode testing, its ChatGPT Bridge setup wizard selects the
approved library and tunnel client, stores the runtime key securely, verifies
the local bridge, and records redacted tunnel diagnostics.
[Desktop guide](docs/desktop-app-getting-started.md).

<img src="docs/assets/readme/hero-grounded-answer.png" alt="VERA desktop app with a document library, an answer with citations, and the supporting passage highlighted in the source PDF" width="85%">

## Learn more

- [Getting started](docs/getting-started.md) · [CLI reference](docs/cli-reference.md) · [Recipes](docs/examples.md)
- [Conversion](docs/conversion.md) · [Search](docs/searching.md) · [Libraries](docs/document-libraries.md)
- [Validation and export](docs/validation-and-export.md) · [Retrieval evaluation](docs/evaluation.md)
- [Format specification](docs/vera-spec-v0.2.md) · [Architecture](docs/architecture.md) · [Packages](packages/README.md)
- [Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md) · [Roadmap](ROADMAP.md) · [Troubleshooting](docs/troubleshooting.md)

VERA is experimental and pre-1.0. Release **0.3.x** versions the software;
the archive format remains **0.2**. Licensed under [Apache-2.0](LICENSE).
