"""Word (.docx) parser: headings, lists, and tables in document order."""

from __future__ import annotations

from docx import Document
from docx.oxml import parse_xml
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from vera_ingest.types import ParsedBlock, ParsedPage

from .common import MarkdownPreview, OfficeBlock, gfm_table, text_span


def _heading_level(paragraph: Paragraph) -> int | None:
    style = paragraph.style
    name = style.name if style is not None else ""
    if name == "Title":
        return 1
    if name.startswith("Heading "):
        suffix = name.removeprefix("Heading ").strip()
        if suffix.isdigit():
            return int(suffix)
    return None


def _is_list(paragraph: Paragraph) -> bool:
    properties = paragraph._p.pPr
    if properties is not None and properties.numPr is not None:
        return True
    style = paragraph.style
    name = style.name if style is not None else ""
    return name.startswith("List")


def _iter_body(document: Document):
    parent = document
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, parent)
        elif child.tag == qn("w:tbl"):
            yield Table(child, parent)


def _tc_text(tc) -> str:
    """Join the visible text in one table cell, including nested tables."""
    parts: list[str] = []
    for paragraph in tc.iter(qn("w:p")):
        text = "".join(node.text or "" for node in paragraph.iter(qn("w:t"))).strip()
        if text:
            parts.append(text)
    return " ".join(parts)


def _short_error(exc: BaseException) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    if len(message) > 180:
        return message[:177] + "..."
    return message


def _element_has_text(element) -> bool:
    return any((node.text or "").strip() for node in element.iter(qn("w:t")))


def _related_part_has_text(document: Document, reltype: str) -> bool:
    try:
        rels = document.part.rels.values()
    except Exception:
        return False
    for rel in rels:
        if getattr(rel, "reltype", None) != reltype:
            continue
        try:
            blob = rel.target_part.blob
        except Exception:
            return True
        if b"w:t" not in blob:
            continue
        try:
            root = parse_xml(blob)
        except Exception:
            return True
        if _element_has_text(root):
            return True
    return False


def _unread_part_warnings(document: Document) -> list[str]:
    """Note text the body walker does not extract."""
    warnings: list[str] = []
    header_text = False
    try:
        stories = []
        for section in document.sections:
            stories.extend(
                (
                    section.header,
                    section.footer,
                    section.first_page_header,
                    section.first_page_footer,
                    section.even_page_header,
                    section.even_page_footer,
                )
            )
        header_text = any(_element_has_text(story._element) for story in stories)
    except Exception as exc:
        warnings.append(f"Headers and footers could not be checked ({_short_error(exc)}).")
    else:
        if header_text:
            warnings.append("Header and footer text was left out of search.")
    notes = (
        (
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes",
            "Footnotes were left out of search.",
        ),
        (
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/endnotes",
            "Endnotes were left out of search.",
        ),
        (
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments",
            "Comments were left out of search.",
        ),
    )
    for reltype, message in notes:
        if _related_part_has_text(document, reltype):
            warnings.append(message)
    body = document.element.body
    if any(
        child.tag == qn("w:sdt") and _element_has_text(child)
        for child in body.iterchildren()
    ):
        warnings.append("Text inside content controls was left out of search.")
    if any(_element_has_text(node) for node in body.iter(qn("w:txbxContent"))):
        warnings.append("Text boxes were left out of search.")
    if any(True for _ in body.iter(qn("w:altChunk"))):
        warnings.append("An embedded alternate chunk was left out of search.")
    return warnings


def _table_rows(table: Table) -> list[list[str]]:
    """Read each row from its ``w:tc`` elements.

    ``row.cells`` asks python-docx to rebuild a rectangular layout grid. Merged
    cells whose spans do not start on an exact grid column raise
    ``ValueError: no tc element at grid_offset``. The cell text is still stored
    on the ``w:tc`` elements, so read those directly.
    """
    return [[_tc_text(tc) for tc in tr.tc_lst] for tr in table._tbl.tr_lst]


def parse_docx(
    source_path: str,
) -> tuple[list[ParsedPage], list[OfficeBlock], str, list[str]]:
    """Return pages, blocks, the Markdown preview, and part-skip warnings.

    A corrupt or encrypted package still raises. One unreadable paragraph or
    table is recorded and the rest of the document is kept.
    """
    document = Document(source_path)
    preview = MarkdownPreview()
    blocks: list[OfficeBlock] = []
    try:
        warnings = _unread_part_warnings(document)
    except Exception as exc:
        warnings = [f"Some document parts could not be checked ({_short_error(exc)})."]
    unread_paragraphs = 0
    unread_tables = 0
    first_error = ""

    def add(block_type: str, text: str, *, heading_level: int | None = None, markdown: str) -> None:
        if not text.strip():
            return
        start, end, end_column = preview.add(markdown)
        blocks.append(
            OfficeBlock(
                parsed=ParsedBlock(
                    page_number=1,
                    block_type=block_type,
                    text=text,
                    heading_level=heading_level,
                ),
                region=text_span(start, end, end_column),
            )
        )

    for item in _iter_body(document):
        try:
            if isinstance(item, Paragraph):
                text = item.text.strip()
                if not text:
                    continue
                level = _heading_level(item)
                if level is not None:
                    add("heading", text, heading_level=level, markdown=f"{'#' * level} {text}")
                elif _is_list(item):
                    add("list", text, markdown=f"- {text}")
                else:
                    add("paragraph", text, markdown=text)
            else:
                rows = _table_rows(item)
                rendered = gfm_table(rows)
                if rendered.strip():
                    add("table", rendered, markdown=rendered)
        except Exception as exc:
            if isinstance(item, Paragraph):
                unread_paragraphs += 1
            else:
                unread_tables += 1
            if not first_error:
                first_error = _short_error(exc)

    if unread_paragraphs or unread_tables:
        parts: list[str] = []
        if unread_paragraphs:
            parts.append(
                f"{unread_paragraphs} paragraph" + ("s" if unread_paragraphs != 1 else "")
            )
        if unread_tables:
            parts.append(f"{unread_tables} table" + ("s" if unread_tables != 1 else ""))
        detail = f" ({first_error})" if first_error else ""
        warnings.append(f"{' and '.join(parts)} could not be read{detail}.")
    if warnings:
        warnings.append("Search covers the extracted text.")

    body = preview.text()
    page = ParsedPage(page_number=1, width=None, height=None, text=body)
    return [page], blocks, body, warnings
