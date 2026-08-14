"""Page rasterization for lab reports."""

from __future__ import annotations

import base64
import re
from typing import Any


def parse_page_selection(
    pages: str | None,
    *,
    max_pages: int,
    page_count: int,
) -> tuple[list[int], bool]:
    """Return selected 1-based page numbers and whether any were omitted.

    ``pages`` may be a comma-separated list of numbers and ranges (``1-5,8``).
    When omitted, the first ``max_pages`` pages are selected.
    """
    if page_count <= 0:
        return [], False
    if pages:
        selected: set[int] = set()
        for part in pages.split(","):
            token = part.strip()
            if not token:
                continue
            if "-" in token:
                start_text, end_text = token.split("-", 1)
                start = int(start_text.strip())
                end = int(end_text.strip())
                if start > end:
                    start, end = end, start
                selected.update(range(start, end + 1))
            else:
                selected.add(int(token))
        ordered = [page for page in sorted(selected) if 1 <= page <= page_count]
        omitted = len(ordered) < page_count or any(
            page < 1 or page > page_count for page in selected
        )
        if len(ordered) > max_pages:
            ordered = ordered[:max_pages]
            omitted = True
        return ordered, omitted or len(ordered) < page_count

    limit = min(max_pages, page_count)
    return list(range(1, limit + 1)), limit < page_count


def rasterize_pages(
    source_bytes: bytes,
    page_numbers: list[int],
    *,
    dpi: int = 96,
) -> dict[int, dict[str, Any]]:
    """Render selected PDF pages to PNG data URLs.

    Returns a mapping of page_number -> {data_url, width, height}.
    """
    import fitz

    if dpi < 36 or dpi > 300:
        raise ValueError("dpi must be between 36 and 300")

    rendered: dict[int, dict[str, Any]] = {}
    document = fitz.open(stream=source_bytes, filetype="pdf")
    try:
        for page_number in page_numbers:
            if page_number < 1 or page_number > document.page_count:
                continue
            page = document.load_page(page_number - 1)
            pixmap = page.get_pixmap(dpi=dpi)
            png = pixmap.tobytes("png")
            data_url = f"data:image/png;base64,{base64.b64encode(png).decode('ascii')}"
            rendered[page_number] = {
                "data_url": data_url,
                "width": pixmap.width,
                "height": pixmap.height,
            }
    finally:
        document.close()
    return rendered


_RANGE_RE = re.compile(r"^\d+(-\d+)?(,\d+(-\d+)?)*$")


def validate_pages_arg(pages: str | None) -> str | None:
    """Return ``pages`` after a light format check, or raise ValueError."""
    if pages is None or pages.strip() == "":
        return None
    cleaned = pages.replace(" ", "")
    if not _RANGE_RE.match(cleaned):
        raise ValueError(f"Invalid --pages value {pages!r}; expected forms like '1-5,8' or '3'")
    return cleaned
