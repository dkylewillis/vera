"""Desktop layout report for one converted archive.

``vera-app`` depends on ``vera-lab``, and the packaged sidecar includes it.
"""

from __future__ import annotations

from pathlib import Path

from vera_app.types import Request
from vera_doc import VeraDocument
from vera_lab import build_report

# Drawing sets and ordinary manuals fit. Larger archives keep the lab's own
# "showing N of M" note in the HTML.
MAX_LAYOUT_LAB_PAGES = 200


def layout_report_filename(archive_path: Path) -> str:
    """``manual.pdf.vera`` becomes ``manual.pdf.lab.html``."""
    name = archive_path.name
    if name.lower().endswith(".vera"):
        name = name[: -len(".vera")]
    else:
        name = archive_path.stem
    return f"{name}.lab.html"


def layout_report_destination(archive: Path, output_dir: Path) -> Path:
    """Put the report under the archive's own folders.

    ``E:/Plans/North/manual.pdf.vera`` becomes
    ``<output>/E/Plans/North/manual.pdf.lab.html``. Two archives that share a
    file name and live in different folders therefore stay apart, and running
    the report again replaces that same file.
    """
    resolved = archive.expanduser().resolve()
    parent = resolved.parent
    anchor = parent.anchor
    relative_parent = parent.relative_to(anchor) if anchor else Path()
    destination = output_dir.joinpath(
        _anchor_folder(anchor),
        relative_parent,
        layout_report_filename(resolved),
    )
    root = output_dir.expanduser().resolve()
    resolved_destination = destination.resolve()
    if root != resolved_destination and root not in resolved_destination.parents:
        raise ValueError("Layout report path escaped the chosen folder.")
    return destination


def _anchor_folder(anchor: str) -> str:
    text = anchor.replace("\\", "/").strip("/")
    if len(text) >= 2 and text[1] == ":":
        return text[0]
    if text.endswith(":"):
        text = text[:-1]
    return text or "root"


def layout_lab(request: Request) -> dict[str, object]:
    """Write a vera-lab HTML report for one ``.vera`` archive."""
    raw_path = str(request.get("path") or "").strip()
    raw_dir = str(request.get("output_dir") or "").strip()
    if not raw_path:
        raise ValueError("Choose a converted .vera archive.")
    archive = Path(raw_path)
    if archive.suffix.lower() != ".vera" or not archive.is_file():
        raise ValueError("Layout report reads a converted .vera archive.")
    if not raw_dir:
        raise ValueError("Choose a folder in Settings → Layout lab.")
    output_dir = Path(raw_dir)
    if output_dir.exists() and not output_dir.is_dir():
        raise ValueError("The layout report folder is not a folder.")

    document = VeraDocument.open(archive)
    try:
        pages = int(document.inspect().get("pages") or 0)
    finally:
        document.close()
    max_pages = pages if 0 < pages <= MAX_LAYOUT_LAB_PAGES else MAX_LAYOUT_LAB_PAGES
    output = layout_report_destination(archive, output_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    written = build_report(archive, output, max_pages=max_pages)
    return {
        "path": written,
        "pages": pages,
        "max_pages": max_pages,
        "pages_omitted": pages > MAX_LAYOUT_LAB_PAGES,
    }
