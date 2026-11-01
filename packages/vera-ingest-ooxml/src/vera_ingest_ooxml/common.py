"""Shared block and preview types for OOXML parsers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from vera_ingest.types import ParsedBlock

FIGURE_LINK_SCHEME = "vera-figure:"


def block_id_for(index: int) -> str:
    """Block id for the 1-based position of a block in parser output."""
    return f"block_{index:06d}"


@dataclass
class OfficeBlock:
    """One layout block plus the locator written onto its ingest region."""

    parsed: ParsedBlock
    region: dict[str, object] = field(default_factory=dict)
    citation_label: str = ""


def sheet_citation(name: str, cell_range: str) -> str:
    """Return an Excel-style ``Sheet!A1:F40`` label, quoting names that need it."""
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        return f"{name}!{cell_range}"
    escaped = name.replace("'", "''")
    return f"'{escaped}'!{cell_range}"


def markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def gfm_table(rows: list[list[str]]) -> str:
    """Render rows as a GitHub-flavored Markdown table. The first row is the header."""
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    padded = [row + [""] * (width - len(row)) for row in rows]
    header = padded[0]
    lines = [
        "| " + " | ".join(markdown_cell(cell) for cell in header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in padded[1:]:
        lines.append("| " + " | ".join(markdown_cell(cell) for cell in row) + " |")
    return "\n".join(lines)


class MarkdownPreview:
    """Markdown built in the same pass as Word blocks, so line spans stay aligned."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def add(self, text: str) -> tuple[int, int, int]:
        """Append a block and return 1-based start line, end line, and end column."""
        block_lines = text.splitlines() or [""]
        if self.lines:
            self.lines.append("")
        start = len(self.lines) + 1
        self.lines.extend(block_lines)
        end = len(self.lines)
        end_column = max(1, len(self.lines[-1]))
        return start, end, end_column

    def text(self) -> str:
        if not self.lines:
            return ""
        return "\n".join(self.lines) + "\n"


def text_span(start: int, end: int, end_column: int) -> dict[str, object]:
    return {
        "kind": "text_span",
        "start": {"line": start, "column": 1},
        "end": {"line": end, "column": end_column},
    }
