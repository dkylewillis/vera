import json
import re
from pathlib import Path

from helpers.cli import leaf_commands as _leaf_commands
from vera_cli.main import build_parser
from vera_doc import ChunkRecord, VeraDocument

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
        # This skill documents the CLI only; mcp is out of scope.
        if path == ("mcp",):
            continue
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
    assert "`skipped_semantic_model_groups`" in agents
    assert "vera mcp` is a long-running stdio server and does not accept `--json`" in agents


def test_portable_skill_documents_hardened_library_contracts():
    skill = SKILL_FILE.read_text(encoding="utf-8")
    reference = CLI_REFERENCE.read_text(encoding="utf-8")

    assert "`malformed_existing`" in skill
    assert "`source_file_hash`" in skill
    assert "`skipped_existing`" in reference
    assert "`source_file_hash`" in reference
    assert "`skipped_files`" in skill
    assert "`skipped_semantic_model_groups`" in skill
    assert "--pipeline-option KEY=VALUE" in skill
    assert "compatibility aliases" in skill
    assert '"malformed_existing": [' in reference
    assert '"skipped_files": [' in reference
    assert '"skipped_semantic_model_groups": [' in reference
    assert "`--pipeline-option KEY=VALUE`" in reference
    assert "Compatibility alias" in reference or "compatibility alias" in reference
    assert "Docling defaults:" in reference
    assert "Markdown defaults:" in reference
    assert "current source file" in skill
    assert "current source file" in reference
    assert "A missing key fails the predicate" in reference
    assert "whitespace-split words" in reference
    assert "ocr_language=en" in reference
    assert "does not receive" in reference
    assert "does not receive this alias" in reference
    assert "deletes every other generation directory" in reference
    assert "does not call `preflight_embedder`" in reference
    assert "single `.vera` archive" in reference
    assert "clamps overlap to `chunk_size - 1`" in reference
    assert "opens one `.vera` archive" in skill
    assert "delete previous" in skill


def _first_json_fence_after(text: str, heading: str) -> dict:
    start = text.index(heading)
    fence = text.index("```json", start)
    body = text[fence + len("```json") :]
    end = body.index("```")
    return json.loads(body[:end])


def test_skill_validate_json_example_keys_are_subset_of_actual(tmp_path):
    archive = tmp_path / "sample.vera"
    with VeraDocument.create(str(archive)) as doc:
        doc.add([ChunkRecord(id="c1", text="hello world")])
        actual = doc.validate()

    example = _first_json_fence_after(
        CLI_REFERENCE.read_text(encoding="utf-8"),
        "### `vera validate FILE`",
    )
    actual_payload_keys = set(actual) | {"file", "path"}
    assert set(example) <= actual_payload_keys
    assert {"chunks", "embeddings", "fts_rows", "attachments"} <= set(example["counts"])
    assert set(example["counts"]) <= set(actual["counts"])
    assert {"file", "path"} <= set(example)


def test_skill_inspect_json_example_includes_file_and_path():
    example = _first_json_fence_after(
        CLI_REFERENCE.read_text(encoding="utf-8"),
        "### `vera inspect FILE`",
    )
    assert {"file", "path"} <= set(example)


def test_skill_get_json_example_includes_citation_fields():
    example = _first_json_fence_after(
        CLI_REFERENCE.read_text(encoding="utf-8"),
        "### `vera get FILE CHUNK_ID`",
    )
    assert {"ok", "file", "path", "chunk_id", "text"} <= set(example)
    assert "score" not in example


def test_skill_documents_mcp_search_default_top_k():
    reference = CLI_REFERENCE.read_text(encoding="utf-8")
    assert "`top_k` to `10`" in reference
    assert "Original source document is not stored in this archive" in reference
