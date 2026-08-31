"""Block parser for Markdown ingest.

This is a retrieval-oriented splitter, not a CommonMark renderer: it yields
headings, paragraphs, lists, fenced code, and GFM tables with 1-based line
spans for ``text_span`` locators.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..types import ParsedBlock, ParsedPage

_ATX_RE = re.compile(r"^(#{1,6})(?:[ \t]+(.*))?$")
_FENCE_RE = re.compile(r"^( {0,3})([`~]{3,})(.*)$")
_THEMATIC_RE = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
_SETEXT_RE = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
_LIST_RE = re.compile(r"^ {0,3}(?:[-*+]|\d+[.)])[ \t]+")
_TABLE_DELIM_CELL_RE = re.compile(r"^:?-{3,}:?$")


@dataclass(frozen=True)
class MarkdownBlock:
    """One layout block plus its source span in the original Markdown."""

    parsed: ParsedBlock
    start_line: int
    end_line: int
    start_column: int
    end_column: int

    def region(self) -> dict[str, object]:
        return {
            "kind": "text_span",
            "start": {"line": self.start_line, "column": self.start_column},
            "end": {"line": self.end_line, "column": self.end_column},
        }


def _end_column(line: str) -> int:
    return max(1, len(line))


def _atx_heading(line: str) -> tuple[int, str] | None:
    stripped = line.strip()
    match = _ATX_RE.match(stripped)
    if not match:
        return None
    marks = match.group(1)
    rest = match.group(2)
    if rest is None:
        if stripped != marks:
            return None
        return len(marks), ""
    text = rest.strip()
    if text.endswith("#"):
        text = text.rstrip("#").rstrip()
    return len(marks), text


def _setext_level(line: str) -> int | None:
    match = _SETEXT_RE.match(line)
    if not match:
        return None
    return 1 if match.group(1).startswith("=") else 2


def _fence_open(line: str) -> tuple[str, int] | None:
    match = _FENCE_RE.match(line.rstrip("\n"))
    if not match:
        return None
    marker = match.group(2)[0]
    length = len(match.group(2))
    return marker, length


def _fence_close(line: str, marker: str, length: int) -> bool:
    match = _FENCE_RE.match(line.rstrip("\n"))
    if not match:
        return False
    closing = match.group(2)
    return closing[0] == marker and len(closing) >= length and not match.group(3).strip()


def _is_thematic_break(line: str) -> bool:
    stripped = line.strip()
    if not stripped or "|" in stripped:
        return False
    return bool(_THEMATIC_RE.match(line))


def _is_list_item(line: str) -> bool:
    return bool(_LIST_RE.match(line))


def _is_table_delimiter(line: str) -> bool:
    if "|" not in line:
        return False
    cells = [cell.strip().replace(" ", "") for cell in line.strip().strip("|").split("|")]
    return bool(cells) and all(_TABLE_DELIM_CELL_RE.match(cell or "") for cell in cells)


def _looks_like_table_row(line: str) -> bool:
    stripped = line.strip()
    return "|" in stripped and not _is_thematic_break(line)


def parse_markdown(text: str) -> tuple[list[ParsedPage], list[MarkdownBlock]]:
    """Split Markdown into a single logical page and structured blocks."""
    body = text.lstrip("\ufeff")
    lines = body.splitlines()
    blocks: list[MarkdownBlock] = []
    index = 0
    total = len(lines)

    def emit(
        block_type: str,
        content: str,
        start: int,
        end: int,
        heading_level: int | None = None,
    ) -> None:
        if not content.strip() and block_type != "heading":
            return
        start_line = start
        end_line = max(start, end)
        last = lines[end_line - 1] if 0 < end_line <= len(lines) else ""
        blocks.append(
            MarkdownBlock(
                parsed=ParsedBlock(
                    page_number=1,
                    block_type=block_type,
                    text=content,
                    heading_level=heading_level,
                ),
                start_line=start_line,
                end_line=end_line,
                start_column=1,
                end_column=_end_column(last),
            )
        )

    if total >= 2 and lines[0].strip() == "---":
        closer = 1
        while closer < total and lines[closer].strip() != "---":
            closer += 1
        if closer < total:
            emit("paragraph", "\n".join(lines[0 : closer + 1]), 1, closer + 1)
            index = closer + 1

    while index < total:
        line = lines[index]
        if not line.strip():
            index += 1
            continue

        fence = _fence_open(line)
        if fence:
            marker, length = fence
            start = index
            index += 1
            while index < total and not _fence_close(lines[index], marker, length):
                index += 1
            if index < total:
                index += 1
            emit("code", "\n".join(lines[start:index]), start + 1, index)
            continue

        heading = _atx_heading(line)
        if heading:
            level, title = heading
            emit("heading", title, index + 1, index + 1, heading_level=level)
            if title.strip():
                emit("paragraph", title, index + 1, index + 1)
            index += 1
            continue

        if index + 1 < total:
            setext = _setext_level(lines[index + 1])
            if setext and line.strip() and not _is_list_item(line):
                title = line.strip()
                emit("heading", title, index + 1, index + 2, heading_level=setext)
                emit("paragraph", title, index + 1, index + 1)
                index += 2
                continue

        if _is_thematic_break(line):
            index += 1
            continue

        if (
            _looks_like_table_row(line)
            and index + 1 < total
            and _is_table_delimiter(lines[index + 1])
        ):
            start = index
            index += 2
            while index < total and _looks_like_table_row(lines[index]):
                index += 1
            emit("table", "\n".join(lines[start:index]), start + 1, index)
            continue

        if _is_list_item(line):
            while index < total:
                current = lines[index]
                if not current.strip():
                    if index + 1 < total and (
                        _is_list_item(lines[index + 1]) or lines[index + 1][:1] in {" ", "\t"}
                    ):
                        index += 1
                        continue
                    break
                if _is_list_item(current) or current[:1] in {" ", "\t"}:
                    emit("paragraph", current.strip(), index + 1, index + 1)
                    index += 1
                    continue
                break
            continue

        start = index
        collected = [line]
        index += 1
        while index < total and lines[index].strip():
            nxt = lines[index]
            if (
                _fence_open(nxt)
                or _atx_heading(nxt)
                or _is_thematic_break(nxt)
                or _is_list_item(nxt)
            ):
                break
            if index + 1 < total and _setext_level(lines[index + 1]) and not _is_list_item(nxt):
                break
            if (
                _looks_like_table_row(nxt)
                and index + 1 < total
                and _is_table_delimiter(lines[index + 1])
            ):
                break
            collected.append(nxt)
            index += 1
        emit("paragraph", "\n".join(collected), start + 1, start + len(collected))

    page = ParsedPage(page_number=1, width=None, height=None, text=body)
    return [page], blocks
