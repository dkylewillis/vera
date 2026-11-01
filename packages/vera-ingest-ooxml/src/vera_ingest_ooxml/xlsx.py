"""Excel (.xlsx) parser: each sheet becomes header-repeating row-group tables."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from vera_ingest.types import ParsedBlock, ParsedPage

from .common import OfficeBlock, gfm_table, sheet_citation

PREVIEW_ROW_LIMIT = 200
PREVIEW_COLUMN_LIMIT = 30


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, float):
        return format(value, "g")
    return str(value).replace("\n", " ").strip()


def _trim_trailing_empty(rows: list[list[str]]) -> list[list[str]]:
    trimmed = list(rows)
    while trimmed and not any(cell for cell in trimmed[-1]):
        trimmed.pop()
    if not trimmed:
        return []
    width = max(len(row) for row in trimmed)
    while width > 0 and all(len(row) < width or not row[width - 1] for row in trimmed):
        width -= 1
    return [row[:width] for row in trimmed]


def _sheet_rows(source_path: str) -> list[tuple[str, int, list[list[str]]]]:
    """Return (title, 1-based sheet index, rows) for every sheet.

    Cached formula values win. A formula Excel has not calculated is kept as
    its formula text so the cell is still searchable.
    """
    values = load_workbook(source_path, read_only=True, data_only=True)
    formulas = load_workbook(source_path, read_only=True, data_only=False)
    sheets: list[tuple[str, int, list[list[str]]]] = []
    try:
        for index, (value_sheet, formula_sheet) in enumerate(
            zip(values.worksheets, formulas.worksheets),
            start=1,
        ):
            rows: list[list[str]] = []
            for value_row, formula_row in zip(
                value_sheet.iter_rows(values_only=True),
                formula_sheet.iter_rows(values_only=True),
            ):
                cells: list[str] = []
                for value, formula in zip(value_row, formula_row):
                    text = _cell_text(value)
                    if not text and isinstance(formula, str) and formula.startswith("="):
                        text = formula
                    cells.append(text)
                rows.append(cells)
            sheets.append((value_sheet.title, index, _trim_trailing_empty(rows)))
    finally:
        values.close()
        formulas.close()
    return sheets


def _pad(row: list[str], width: int) -> list[str]:
    return row + [""] * (width - len(row))


def parse_xlsx(
    source_path: str,
    *,
    rows_per_chunk: int = 40,
) -> tuple[list[ParsedPage], list[OfficeBlock], dict[str, object]]:
    """Return pages, row-group blocks, and the bounded sheet preview payload."""
    if rows_per_chunk < 1:
        raise ValueError("rows_per_chunk must be positive")
    pages: list[ParsedPage] = []
    blocks: list[OfficeBlock] = []
    preview_sheets: list[dict[str, object]] = []
    for title, sheet_index, rows in _sheet_rows(source_path):
        if not rows or not any(any(cell for cell in row) for row in rows):
            continue
        width = max(len(row) for row in rows)
        header_index = next(index for index, row in enumerate(rows) if any(row))
        header = _pad(rows[header_index], width)
        data = [_pad(row, width) for row in rows[header_index + 1 :]]
        header_row = header_index + 1
        groups = [data[start : start + rows_per_chunk] for start in range(0, len(data), rows_per_chunk)]
        if not groups:
            groups = [[]]
        last_column = get_column_letter(width)
        page_lines = [title]
        blocks.append(
            OfficeBlock(
                parsed=ParsedBlock(
                    page_number=sheet_index,
                    block_type="heading",
                    text=title,
                    heading_level=1,
                ),
                region={"kind": "sheet_range", "sheet": title, "range": f"A{header_row}:{last_column}{header_row}"},
                citation_label=sheet_citation(title, f"A{header_row}:{last_column}{header_row}"),
            )
        )
        for group_index, group in enumerate(groups):
            if group:
                start_row = header_row + 1 + group_index * rows_per_chunk
                end_row = start_row + len(group) - 1
            else:
                start_row = header_row
                end_row = header_row
            cell_range = f"A{header_row}:{last_column}{end_row}"
            rendered = gfm_table([header, *group])
            page_lines.append(rendered)
            blocks.append(
                OfficeBlock(
                    parsed=ParsedBlock(
                        page_number=sheet_index,
                        block_type="table",
                        text=rendered,
                    ),
                    region={"kind": "sheet_range", "sheet": title, "range": cell_range},
                    citation_label=sheet_citation(title, cell_range),
                )
            )
        pages.append(
            ParsedPage(
                page_number=sheet_index,
                width=None,
                height=None,
                text="\n".join(page_lines),
            )
        )
        preview_sheets.append(
            {
                "name": title,
                "page": sheet_index,
                "row_count": len(rows),
                "column_count": width,
                "rows": [row[:PREVIEW_COLUMN_LIMIT] for row in rows[:PREVIEW_ROW_LIMIT]],
            }
        )
    preview = {
        "preview_row_limit": PREVIEW_ROW_LIMIT,
        "preview_column_limit": PREVIEW_COLUMN_LIMIT,
        "sheets": preview_sheets,
    }
    return pages, blocks, preview
