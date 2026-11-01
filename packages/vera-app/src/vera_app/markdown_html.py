"""Pre-render cached Markdown previews to HTML for the desktop viewer."""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from pathlib import Path

from markdown_it import MarkdownIt
from markdown_it.token import Token

from vera_app.cancellation import CancellationToken

# Bump when the generated markup changes so stale cache files are not reused.
MARKDOWN_HTML_VERSION = 2

# Word previews link each picture as `![alt](vera-figure:<block_id>)`.
FIGURE_LINK_SCHEME = "vera-figure:"

# Block tokens that carry source line ranges. These are the elements the
# viewer highlights for a `text_span` citation.
_LINE_TOKENS = frozenset(
    {
        "paragraph_open",
        "heading_open",
        "list_item_open",
        "table_open",
        "blockquote_open",
        "fence",
        "code_block",
    }
)


def _parser() -> MarkdownIt:
    # html=False escapes raw HTML in the document, and markdown-it rejects
    # javascript:/vbscript:/file: links, so the output is safe to insert.
    return MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])


def _figure_image(image: Token, figures: Mapping[str, str]) -> None:
    """Point a `vera-figure:` image at its cached file, or show its alt text."""
    src = str(image.attrGet("src") or "")
    if not src.startswith(FIGURE_LINK_SCHEME):
        return
    image.attrs.pop("src", None)
    cached = figures.get(src.removeprefix(FIGURE_LINK_SCHEME))
    if cached:
        # The renderer resolves this against the HTML file's vera-source URL.
        image.attrSet("data-vera-src", cached)
        image.attrSet("class", "markdownFigure")
        image.attrSet("loading", "lazy")
        return
    image.type = "text"
    image.content = f"[Figure: {image.content or 'not shown'}]"
    image.children = None


def render_markdown_html(text: str, figures: Mapping[str, str] | None = None) -> str:
    """Render Markdown with ``data-ls``/``data-le`` 1-based source line ranges.

    Line numbers match ``markdownDisplayLines()`` in the renderer: one leading
    UTF-8 BOM is dropped before counting. ``figures`` maps a Word preview's
    block ids to cache-relative image paths.
    """
    if text.startswith("\ufeff"):
        text = text[1:]
    md = _parser()
    tokens = md.parse(text)
    for token in tokens:
        if token.map and token.type in _LINE_TOKENS:
            token.attrSet("data-ls", str(token.map[0] + 1))
            token.attrSet("data-le", str(token.map[1]))
        for child in token.children or ():
            if child.type == "link_open":
                child.attrSet("target", "_blank")
                child.attrSet("rel", "noreferrer")
            elif child.type == "image":
                _figure_image(child, figures or {})
    return md.renderer.render(tokens, md.options, {})


def markdown_html_path(cache_path: Path) -> Path:
    return cache_path.with_name(f"{cache_path.stem}.v{MARKDOWN_HTML_VERSION}.html")


def ensure_markdown_html(
    cache_path: Path,
    cancel: CancellationToken | None = None,
    figures: Callable[[], Mapping[str, str]] | None = None,
) -> Path:
    """Write (or reuse) the HTML rendering beside a cached Markdown file.

    ``figures`` runs only when the HTML is rebuilt, so cache hits never open
    the archive.
    """
    html_path = markdown_html_path(cache_path)
    if html_path.is_file() and html_path.stat().st_mtime_ns >= cache_path.stat().st_mtime_ns:
        return html_path
    if cancel:
        cancel.raise_if_cancelled()
    html = render_markdown_html(
        cache_path.read_text(encoding="utf-8", errors="replace"),
        figures() if figures else None,
    )
    if cancel:
        cancel.raise_if_cancelled()
    tmp_path = html_path.with_name(f"{html_path.name}.{threading.get_ident()}.tmp")
    try:
        tmp_path.write_text(html, encoding="utf-8")
        tmp_path.replace(html_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
    return html_path
