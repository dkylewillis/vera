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
        *DOCS.glob("*.md"),
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
    index = (DOCS / "README.md").read_text(encoding="utf-8")
    guides = {
        "getting-started.md",
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
