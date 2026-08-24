from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERA_DOC = ROOT / "packages" / "vera-doc"


def test_vera_doc_does_not_import_outer_packages() -> None:
    banned_prefixes = (
        "vera_ingest",
        "vera_mcp",
        "vera_cli",
        "vera_app",
        "fitz",
        "pdfplumber",
        "mcp",
    )
    violations: list[str] = []
    for path in (VERA_DOC / "src" / "vera_doc").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.startswith(banned_prefixes):
                    violations.append(f"{path.relative_to(ROOT)} imports {name}")
    assert violations == []


def test_vera_doc_has_no_extraction_modules_or_dependencies() -> None:
    package_root = VERA_DOC / "src" / "vera_doc"
    assert not (package_root / "convert.py").exists()
    assert not (package_root / "ingest").exists()
    assert not (package_root / "evaluate.py").exists()
    assert not list((package_root / "integrations").glob("*.py"))

    metadata = (VERA_DOC / "pyproject.toml").read_text(encoding="utf-8")
    for dependency in ("pymupdf", "pdfplumber", "vera-ingest", "mcp>="):
        assert dependency not in metadata.lower()


def test_conversion_and_mcp_live_in_sibling_packages() -> None:
    assert (ROOT / "packages" / "vera-ingest" / "src" / "vera_ingest" / "convert.py").is_file()
    assert (ROOT / "packages" / "vera-ingest" / "src" / "vera_ingest" / "viewer.py").is_file()
    assert (ROOT / "packages" / "vera-mcp" / "src" / "vera_mcp" / "server.py").is_file()


def _imported_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_sibling_packages_do_not_import_vera_doc_private_modules() -> None:
    siblings = [
        ROOT / "packages" / "vera-ingest" / "src",
        ROOT / "packages" / "vera-ingest-pymupdf" / "src",
        ROOT / "packages" / "vera-ingest-docling" / "src",
        ROOT / "packages" / "vera-cli" / "src",
        ROOT / "packages" / "vera-embed-openai" / "src",
        ROOT / "packages" / "vera-mcp" / "src",
        ROOT / "packages" / "vera-app" / "src",
        ROOT / "packages" / "vera-lab" / "src",
    ]
    violations: list[str] = []
    for src in siblings:
        for path in src.rglob("*.py"):
            for name in _imported_names(path):
                parts = name.split(".")
                if parts[0] != "vera_doc":
                    continue
                if any(part.startswith("_") for part in parts[1:]):
                    violations.append(f"{path.relative_to(ROOT)} imports {name}")
    assert violations == []


def test_vera_doc_has_no_core_subpackage() -> None:
    assert not (VERA_DOC / "src" / "vera_doc" / "core").exists()
    assert (VERA_DOC / "src" / "vera_doc" / "_schema.py").is_file()
    assert (VERA_DOC / "src" / "vera_doc" / "embeddings.py").is_file()
    assert (VERA_DOC / "src" / "vera_doc" / "validation.py").is_file()
    assert (VERA_DOC / "src" / "vera_doc" / "option_parsing.py").is_file()
