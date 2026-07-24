import argparse
import re
from pathlib import Path

from vera_cli.main import build_parser


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "vera"
SKILL_FILE = SKILL_DIR / "SKILL.md"
CLI_REFERENCE = SKILL_DIR / "references" / "cli-reference.md"


def _frontmatter_and_body(text: str) -> tuple[str, str]:
    assert text.startswith("---\n"), "SKILL.md frontmatter must start at byte 0"
    closing = text.find("\n---\n", 4)
    assert closing != -1, "SKILL.md frontmatter must have a closing delimiter"
    return text[4:closing], text[closing + 5 :]


def _frontmatter_value(frontmatter: str, key: str) -> str:
    match = re.search(rf"^{re.escape(key)}:\s*(.+)$", frontmatter, re.MULTILINE)
    assert match, f"missing {key!r} frontmatter field"
    return match.group(1).strip()


def _leaf_commands(
    parser: argparse.ArgumentParser,
    prefix: tuple[str, ...] = (),
) -> list[tuple[tuple[str, ...], argparse.ArgumentParser]]:
    commands: list[tuple[tuple[str, ...], argparse.ArgumentParser]] = []
    subparsers = next(
        (action for action in parser._actions if isinstance(action, argparse._SubParsersAction)),
        None,
    )
    if subparsers is None:
        return [(prefix, parser)]
    for name, child in subparsers.choices.items():
        commands.extend(_leaf_commands(child, (*prefix, name)))
    return commands


def test_portable_skill_frontmatter_and_layout():
    text = SKILL_FILE.read_text(encoding="utf-8")
    frontmatter, body = _frontmatter_and_body(text)

    name = _frontmatter_value(frontmatter, "name")
    description = _frontmatter_value(frontmatter, "description")
    compatibility = _frontmatter_value(frontmatter, "compatibility")

    assert name == SKILL_DIR.name
    assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name)
    assert len(name) <= 64
    assert 1 <= len(description) <= 1024
    assert "Use when" in description
    assert 1 <= len(compatibility) <= 500
    assert _frontmatter_value(frontmatter, "license") == "Apache-2.0"
    assert body.strip()
    assert len(text.splitlines()) < 500


def test_portable_skill_references_are_shallow_and_exist():
    text = SKILL_FILE.read_text(encoding="utf-8")
    links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", text)
    local_links = [link for link in links if "://" not in link and not link.startswith("#")]

    assert local_links
    for link in local_links:
        path = Path(link)
        assert not path.is_absolute()
        assert len(path.parts) <= 2
        assert (SKILL_DIR / path).is_file(), f"missing skill reference: {link}"


def test_cli_reference_covers_parser_commands_and_long_options():
    reference = CLI_REFERENCE.read_text(encoding="utf-8")
    leaves = _leaf_commands(build_parser())

    documented_options: set[str] = set()
    for path, parser in leaves:
        command = " ".join(path)
        assert f"### `vera {command}" in reference, f"undocumented command: vera {command}"
        for action in parser._actions:
            documented_options.update(
                option
                for option in action.option_strings
                if option.startswith("--") and option != "--help"
            )

    for option in sorted(documented_options):
        assert f"`{option}" in reference, f"undocumented option: {option}"


def test_canonical_agent_documentation_links_exist():
    expected = {
        ROOT / "README.md": [
            "skills/vera/SKILL.md",
            "skills/vera/references/cli-reference.md",
            "docs/agent-skills.md",
        ],
        ROOT / "AGENTS.md": [
            "skills/vera/SKILL.md",
            "skills/vera/references/cli-reference.md",
            "docs/agent-skills.md",
        ],
    }
    for document, links in expected.items():
        text = document.read_text(encoding="utf-8")
        for link in links:
            assert link in text
            assert (ROOT / link).is_file()

    assert not (ROOT / "skills" / "vera.md").exists()
    assert not (ROOT / "skills" / "vera-ask.md").exists()


def test_quick_reference_matches_search_json_contract():
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert '"rank":' not in agents
    assert '"file": "manual.vera"' not in agents
    assert '"document_id": "document_0001"' in agents
    assert "vera mcp` is a long-running stdio server and does not accept `--json`" in agents
