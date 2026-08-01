from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERA_DOC = ROOT / "packages" / "vera-doc"


def test_vera_doc_does_not_import_outer_packages() -> None:
    banned_prefixes = (
        "vera_extract",
        "vera_mcp",
        "vera_cli",
        "vera_app",
        "fitz",
        "pdfplumber",
        "mcp",
    )
    violations: list[str] = []
    for path in (VERA_DOC / "src" / "vera").rglob("*.py"):
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
    package_root = VERA_DOC / "src" / "vera"
    assert not (package_root / "convert.py").exists()
    assert not (package_root / "ingest").exists()
    assert not (package_root / "evaluate.py").exists()
    assert not list((package_root / "integrations").glob("*.py"))

    metadata = (VERA_DOC / "pyproject.toml").read_text(encoding="utf-8")
    for dependency in ("pymupdf", "pdfplumber", "vera-extract", "mcp>="):
        assert dependency not in metadata.lower()


def test_conversion_and_mcp_live_in_sibling_packages() -> None:
    assert (
        ROOT / "packages" / "vera-extract" / "src" / "vera_extract" / "convert.py"
    ).is_file()
    assert (
        ROOT / "packages" / "vera-mcp" / "src" / "vera_mcp" / "server.py"
    ).is_file()

