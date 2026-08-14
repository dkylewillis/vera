import argparse
import re
from pathlib import Path
from urllib.parse import unquote

from vera_cli.main import build_parser


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
CLI_REFERENCE = DOCS / "cli-reference.md"


def _leaf_commands(
    parser: argparse.ArgumentParser,
    prefix: tuple[str, ...] = (),
) -> list[tuple[tuple[str, ...], argparse.ArgumentParser]]:
    subparsers = next(
        (action for action in parser._actions if isinstance(action, argparse._SubParsersAction)),
        None,
    )
    if subparsers is None:
        return [(prefix, parser)]
    leaves: list[tuple[tuple[str, ...], argparse.ArgumentParser]] = []
    for name, child in subparsers.choices.items():
        leaves.extend(_leaf_commands(child, (*prefix, name)))
    return leaves


def _documentation_files() -> list[Path]:
    return [
        ROOT / "README.md",
        ROOT / "AGENTS.md",
        *DOCS.rglob("*.md"),
        *(ROOT / "skills" / "vera").rglob("*.md"),
    ]


def test_local_documentation_links_resolve():
    link_pattern = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
    for document in _documentation_files():
        text = document.read_text(encoding="utf-8")
        for raw_target in link_pattern.findall(text):
            target = raw_target.split("#", 1)[0].strip()
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            path = (document.parent / unquote(target)).resolve()
            assert path.exists(), f"{document.relative_to(ROOT)} links to missing {raw_target}"


def test_documentation_index_lists_user_guides():
    index = (DOCS / "user-documentation.md").read_text(encoding="utf-8")
    guides = {
        "getting-started.md",
        "desktop-app-getting-started.md",
        "examples.md",
        "troubleshooting.md",
        "conversion.md",
        "searching.md",
        "document-libraries.md",
        "figures-and-regions.md",
        "validation-and-export.md",
        "evaluation.md",
        "python-api.md",
        "mcp.md",
        "cli-reference.md",
        "library-index-structure.md",
    }
    for guide in guides:
        assert f"]({guide})" in index
        assert (DOCS / guide).is_file()


def test_human_cli_reference_covers_parser_commands_and_options():
    reference = CLI_REFERENCE.read_text(encoding="utf-8")
    options: set[str] = set()
    for path, parser in _leaf_commands(build_parser()):
        command = " ".join(path)
        assert f"## `vera {command}" in reference, f"undocumented command: vera {command}"
        for action in parser._actions:
            options.update(
                option
                for option in action.option_strings
                if option.startswith("--") and option != "--help"
            )
    for option in sorted(options):
        assert f"`{option}" in reference, f"undocumented option: {option}"


def test_documented_cli_examples_parse():
    parser = build_parser()
    examples = [
        ["convert", "input.pdf", "output.vera", "--model", "hashing", "--json"],
        ["inspect", "output.vera", "--json"],
        [
            "search",
            "output.vera",
            "parking requirements",
            "--mode",
            "hybrid",
            "--top-k",
            "5",
            "--context-chunks",
            "1",
            "--figures",
            "--regions",
            "--json",
        ],
        ["index", "build", "library", "--recursive", "--exclude", "archive/**", "--json"],
        ["index", "update", "library", "--json"],
        ["index", "status", "library", "--json"],
        ["validate", "output.vera", "--json"],
        ["export", "output.vera", "exports", "--json"],
        ["eval", "output.vera", "queries.json", "--mode", "all", "--top-k", "5", "--json"],
        ["mcp"],
    ]
    for argv in examples:
        args = parser.parse_args(argv)
        assert callable(args.func)


def test_agents_rule_requires_human_documentation_updates():
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "Keep human and agent documentation current" in agents
    assert "Any user-visible feature change" in agents
    assert "Do not merge a feature whose" in agents


def test_hardening_json_contracts_are_documented():
    conversion = (DOCS / "conversion.md").read_text(encoding="utf-8")
    libraries = (DOCS / "document-libraries.md").read_text(encoding="utf-8")
    desktop = (DOCS / "desktop-app-getting-started.md").read_text(encoding="utf-8")
    desktop_architecture = (DOCS / "desktop-app-architecture.md").read_text(encoding="utf-8")
    mcp = (DOCS / "mcp.md").read_text(encoding="utf-8")
    python_api = (DOCS / "python-api.md").read_text(encoding="utf-8")

    assert "malformed_existing" in conversion
    assert "requires OCR" in conversion
    assert "skipped_files" in libraries
    assert "skipped_semantic_model_groups" in libraries
    assert "does not reopen archives" in libraries
    assert "does not rebuild" in libraries
    assert "summary_complete" in libraries
    assert "Collection indexes are persistent" in desktop
    assert "Use **Inspect** in the Info view" in desktop
    assert "corpus opens on the first" in desktop
    assert "indexing runs in the background" in desktop
    assert "completed archives" in desktop
    assert "finalizing phase" in desktop
    assert "Inspection runs on a sidecar worker" in desktop
    assert "independently of simultaneous indexing or conversion" in desktop
    assert "Selecting another citation supersedes" in desktop
    assert "within two minutes" in desktop
    assert "Answer prose appears incrementally" in desktop
    assert "withholds inline tool-call markup" in desktop
    assert "initially returns only figure metadata" in desktop
    assert "loads image previews" in desktop
    assert "only explicit `search_start` and `search_done`" in desktop_architecture
    assert "Token-level `answer_delta`" in desktop_architecture
    assert "PyMuPDF parser" in desktop
    assert "local hashing embeddings" in desktop
    assert "Hugging Face" in desktop
    assert "HF_TOKEN" in desktop
    assert "Hugging Face" in (DOCS / "packages" / "vera-app.md").read_text(encoding="utf-8")
    assert "`attachment_metadata()`" in python_api
    assert "do not contain a `data` field" in python_api
    assert "allow_empty=True" in libraries
    assert "`skipped_files`" in mcp
    assert "`skipped_semantic_model_groups`" in mcp


def test_figures_storage_map_is_documented():
    figures = (DOCS / "figures-and-regions.md").read_text(encoding="utf-8")
    spec = (DOCS / "vera-spec-v0.2.md").read_text(encoding="utf-8")

    assert "## Storage map (VERA 0.2 schema)" in figures
    for marker in (
        "`chunks`",
        "`metadata_json`",
        '`"regions"`',
        "`attachments`",
        "`chunk_attachments`",
        "`viewer_pages`",
        "`viewer_blocks`",
        "`vera_metadata`",
        "`archive_metadata`",
    ):
        assert marker in figures, f"storage map missing {marker}"
    assert "figures-and-regions.md#storage-map-vera-02-schema" in spec
