# Getting started

This tutorial installs the VERA CLI, converts one PDF into a portable `.vera`
archive, and searches it.

VERA is currently v0.1 and experimental. Preserve source documents and expect
format or API changes before a stable release.

## Requirements

- Python 3.10 or newer
- A local PDF
- Windows, macOS, or Linux

## Install

Install the CLI into your preferred Python environment:

```bash
python -m pip install vera-cli
```

Verify that the console script is available:

```bash
vera --help
```

If `vera` is not on `PATH`, invoke the same CLI as a Python module:

```bash
python -m vera_cli --help
```

Contributors working from a repository checkout should use:

```bash
uv sync --extra dev
uv run vera --help
```

## Convert a PDF

```bash
vera convert "manual.pdf" "manual.vera"
```

The default `hashing` embedding model is local and has no machine-learning
dependency. The resulting archive contains parsed pages, chunks, embeddings,
the keyword index, citation metadata, figures, and the original PDF.

If the output path is omitted, VERA uses the input filename with a `.vera`
suffix:

```bash
vera convert "manual.pdf"
```

## Inspect and validate

Inspect the archive:

```bash
vera inspect "manual.vera"
```

Check its integrity:

```bash
vera validate "manual.vera"
```

A valid archive exits with status 0. An invalid archive exits with status 1 and
prints the issues it found.

## Search

Hybrid search combines semantic and keyword retrieval and is the best default:

```bash
vera search "manual.vera" "stormwater detention requirements" --mode hybrid --top-k 5
```

Each result includes:

- a relevance score;
- source filename;
- page or page range;
- heading path;
- retrieved text.

Use those fields as citations rather than treating the score as evidence. For
example:

```text
Detention is required when ... (manual.pdf, p. 117,
Chapter 4 > Detention Design).
```

## Request structured output

All one-shot commands accept `--json`:

```bash
vera search "manual.vera" "stormwater detention requirements" --top-k 5 --json
```

`vera mcp` is the exception: it is a long-running stdio protocol server, not a
one-shot JSON command.

## Next steps

- Learn how to [choose search modes and refine queries](searching.md).
- [Convert a directory of PDFs](conversion.md).
- [Search and index a document library](document-libraries.md).
- Retrieve [figures and visual highlight regions](figures-and-regions.md).
- [Evaluate retrieval quality](evaluation.md) against expected answers.
- Use VERA from [Python](python-api.md) or an [MCP client](mcp.md).
