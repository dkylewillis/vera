# VERA agent skills

VERA ships a portable
[Agent Skills](https://agentskills.io/specification) package at
[`skills/vera/`](https://github.com/dkylewillis/vera/tree/main/skills/vera/). It teaches a shell-capable AI agent to use
`vera-cli`, interpret its JSON and exit codes, retrieve evidence, and produce
page-level citations.

## Portability

The portable unit is the entire `skills/vera/` directory:

```text
vera/
├── SKILL.md
└── references/
    ├── cli-reference.md
    └── retrieval-workflows.md
```

`SKILL.md` uses only the Agent Skills core fields and relative file references.
It does not call a Hermes-, OpenClaw-, Cursor-, or Claude-specific skill tool.
Compatible clients can therefore use the same files.

Portability has two boundaries:

1. Each client chooses its own skill discovery and installation directories.
2. Client-specific metadata, permission systems, and tool names are not
   portable. The VERA skill describes capabilities such as "run a shell
   command" rather than depending on a named harness tool.

The skill requires:

- Python 3.10 or newer;
- `vera-cli` available as `vera` or importable as `vera_cli`;
- shell execution and access to the local archive paths;
- permission to write only when converting, indexing, or exporting.

## Installation

Copy or symlink the complete `skills/vera/` directory. Do not copy only
`SKILL.md`, because it links to the reference files.

Common project-level convention:

```text
<project>/.agents/skills/vera/
```

Common client locations:

- Hermes: `~/.hermes/skills/vera/`
- OpenClaw managed skill: `~/.openclaw/skills/vera/`
- OpenClaw workspace skill: `<workspace>/skills/vera/`
- Cursor project skill: `<project>/.cursor/skills/vera/`
- Cursor personal skill: `~/.cursor/skills/vera/`

The Agent Skills specification defines the package contents, not installation
paths. Check the active client's documentation if it does not scan one of these
locations.

Install the CLI separately:

```bash
pip install vera-cli
vera --help
```

If the console script is not on `PATH`:

```bash
python -m vera_cli --help
```

Optional capabilities:

- MiniLM neural embeddings require the `vera-doc` `onnx` extra.
- Other Sentence Transformers models require the `vera-doc` `ml` extra.
- The zero-dependency hashing embedder is the default and needs neither extra.

For a repository checkout:

```bash
uv sync --extra dev --extra onnx --extra ml --extra app
uv run vera --help
```

This skill documents the CLI only.

## What the package documents

The main `SKILL.md` stays short enough for activation-time loading. It contains
the default search procedure, retrieval mode decisions, citation rules,
write-safety rules, and failure handling.

The references are loaded only when needed:

- `references/cli-reference.md`: complete command and flag inventory, JSON
  shapes, stdout/stderr behavior, exit codes, and filesystem effects.
- `references/retrieval-workflows.md`: query refinement, exact identifiers,
  corpus and index workflows, figures, visual grounding, evidence assessment,
  and insufficient-evidence responses.

These files are the agent-facing contract. The CLI implementation remains the
software source of truth, and repository tests check the documentation against
the parser.

## Authoring or regenerating a VERA skill

An agent creating an equivalent skill should follow this sequence:

1. Read `packages/vera-cli/src/vera_cli/main.py` for the current command and
   option inventory.
2. Read `packages/vera-cli/src/vera_cli/commands.py` and CLI tests for JSON,
   stdout/stderr, exit codes, and side effects.
3. Use the Agent Skills core frontmatter:

   ```yaml
   ---
   name: vera
   description: <what the skill does and when it should activate>
   license: Apache-2.0
   compatibility: <runtime requirements>
   ---
   ```

4. Keep the main body under 500 lines and put detailed contracts in
   one-level-deep `references/` files.
5. Use relative forward-slash links from `SKILL.md`.
6. Keep installation instructions outside the core procedure or list them by
   client. Do not embed calls such as `skill_view(name="vera")`.
7. Describe write operations explicitly. Search and inspection requests do not
   authorize conversion, overwrite, indexing, or export.
8. Validate the package:

   ```bash
   skills-ref validate ./skills/vera
   ```

9. Run the repository documentation-contract tests and representative CLI
   tests.
10. Test discovery in the target harness with prompts covering direct search,
    corpus search, exact identifiers, figures, and a missing-file failure.

## Cross-harness design rules

For maximum reuse:

- Require only `name` and `description`; use standard `license`,
  `compatibility`, and string metadata when useful.
- Avoid `allowed-tools` unless a deployment knowingly accepts its experimental,
  client-specific interpretation.
- Do not put `metadata.hermes` or `metadata.openclaw` in the portable core.
  Maintain optional wrappers only if a deployment needs gating, configuration,
  scheduling, or environment injection.
- Refer to local files relative to the skill root.
- Never assume a specific shell. Show ordinary commands and call out quoting
  differences only where they matter.
- Do not require a dedicated skill-loading function; compatible agents may load
  `SKILL.md` through ordinary file access.

Hermes and OpenClaw both implement the Agent Skills package shape. Their
extended metadata is useful for deployment-specific behavior but is not needed
to search VERA archives.

## Verification prompts

After installation, test the skill with prompts such as:

- "Search `manual.vera` for detention requirements and cite the answer."
- "Find the pipe sizing table and include its caption."
- "Search every archive under `./library` for termination clauses."
- "Check whether `EL-A` appears as an exact zoning identifier."
- "Validate `manual.vera` and explain any issues."

A successful skill should choose JSON output, inspect exit behavior, refine weak
searches, and cite source filename, page or range, and heading where available.
