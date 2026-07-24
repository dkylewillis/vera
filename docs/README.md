# VERA documentation

VERA packages a source document, parsed structure, embeddings, keyword index,
figures, and citation metadata in one portable `.vera` file.

## Start here

- [Getting started](getting-started.md) — install VERA, convert a PDF, and run
  the first cited search.
- [Examples and recipes](examples.md) — copyable workflows for individual
  documents and document libraries.
- [Troubleshooting](troubleshooting.md) — installation, conversion, search,
  indexing, and optional-dependency problems.

## User guides

- [Convert documents](conversion.md)
- [Search documents](searching.md)
- [Search and index document libraries](document-libraries.md)
- [Work with figures and highlight regions](figures-and-regions.md)
- [Validate archives and export source documents](validation-and-export.md)
- [Evaluate retrieval quality](evaluation.md)
- [Use the Python API](python-api.md)
- [Connect an MCP client](mcp.md)

## Reference

- [CLI reference](cli-reference.md) — command overview with links to the
  exhaustive JSON and exit-code contract.
- [VERA format specification](vera-spec-v0.1.md)
- [Collection index design and behavior](collection-index.md)
- [Portable Agent Skill](../skills/vera/SKILL.md)
- [Agent-skill installation and authoring](agent-skills.md)

## Contributor and architecture documentation

- [Repository architecture](architecture.md)
- [Desktop app architecture](desktop-app-architecture.md)
- [Development handoff](HANDOFF.md)

The README is the product overview, these pages are the human user
documentation, and `skills/vera/` is the self-contained package for AI agents.
When behavior changes, update all affected layers in the same change.
