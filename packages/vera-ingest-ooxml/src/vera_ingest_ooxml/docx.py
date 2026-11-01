"""Word (.docx) parser: headings, lists, tables, and pictures in document order."""

from __future__ import annotations

from dataclasses import dataclass

from docx import Document
from docx.oxml import parse_xml
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from vera_ingest.types import ParsedBlock, ParsedPage

from .common import (
    FIGURE_LINK_SCHEME,
    MarkdownPreview,
    OfficeBlock,
    block_id_for,
    gfm_table,
    text_span,
)

_BLIP = qn("a:blip")
_VML_IMAGEDATA = "{urn:schemas-microsoft-com:vml}imagedata"
_MC_FALLBACK = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"
_DRAWING_FRAMES = frozenset({qn("wp:inline"), qn("wp:anchor")})


@dataclass
class _Picture:
    data: bytes
    ext: str
    alt: str


def _picture_alt(node) -> str:
    for ancestor in node.iterancestors():
        if ancestor.tag in _DRAWING_FRAMES:
            doc_pr = ancestor.find(qn("wp:docPr"))
            if doc_pr is None:
                return ""
            return " ".join((doc_pr.get("descr") or doc_pr.get("title") or "").split())
    return ""


def _pictures(document: Document, element) -> tuple[list[_Picture], int]:
    """Embedded pictures in ``element`` in document order, and how many are linked or unreadable.

    Word stores a VML copy of a drawing under ``mc:Fallback`` for old readers;
    those copies are skipped so each picture appears once.
    """
    pictures: list[_Picture] = []
    unread = 0
    related = document.part.related_parts
    for node in element.iter(_BLIP, _VML_IMAGEDATA):
        if any(ancestor.tag == _MC_FALLBACK for ancestor in node.iterancestors()):
            continue
        rel_id = node.get(qn("r:embed")) if node.tag == _BLIP else node.get(qn("r:id"))
        part = related.get(rel_id) if rel_id else None
        blob = getattr(part, "blob", None)
        if not blob:
            unread += 1
            continue
        ext = str(part.partname).rsplit(".", 1)[-1].lower()
        pictures.append(_Picture(blob, "jpeg" if ext == "jpg" else ext, _picture_alt(node)))
    return pictures, unread


def _markdown_alt(text: str) -> str:
    return text.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


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


def _join_names(names: list[str]) -> str:
    if len(names) <= 2:
        return " and ".join(names)
    return f"{', '.join(names[:-1])}, and {names[-1]}"


def _left_out_note(names: list[str]) -> str:
    """One sentence for parts the body walker leaves out by design."""
    if not names:
        return ""
    listed = _join_names(names)
    return f"{listed[0].upper()}{listed[1:]} aren't included in search. VERA searches the main body text."


def _unread_parts(document: Document) -> tuple[list[str], list[str]]:
    """Return (notes, warnings) for text the body walker does not extract.

    Notes name parts left out by design. Warnings name parts that could not
    be checked.
    """
    warnings: list[str] = []
    left_out: list[str] = []
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
            left_out.extend(("headers", "footers"))
    related_parts = (
        ("http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes", "footnotes"),
        ("http://schemas.openxmlformats.org/officeDocument/2006/relationships/endnotes", "endnotes"),
        ("http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments", "comments"),
    )
    for reltype, name in related_parts:
        if _related_part_has_text(document, reltype):
            left_out.append(name)
    body = document.element.body
    if any(
        child.tag == qn("w:sdt") and _element_has_text(child)
        for child in body.iterchildren()
    ):
        left_out.append("content controls")
    if any(_element_has_text(node) for node in body.iter(qn("w:txbxContent"))):
        left_out.append("text boxes")
    if any(True for _ in body.iter(qn("w:altChunk"))):
        left_out.append("embedded documents")
    if any(True for _ in body.iter(qn("c:chart"))):
        left_out.append("charts")
    note = _left_out_note(left_out)
    return ([note] if note else []), warnings


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
) -> tuple[list[ParsedPage], list[OfficeBlock], str, list[str], list[str]]:
    """Return pages, blocks, the Markdown preview, warnings, and notes.

    Warnings name content that could not be read. Notes name parts left out
    of search by design. A corrupt or encrypted package still raises. One
    unreadable paragraph or table is recorded and the rest is kept.
    """
    document = Document(source_path)
    preview = MarkdownPreview()
    blocks: list[OfficeBlock] = []
    try:
        notes, warnings = _unread_parts(document)
    except Exception as exc:
        notes = []
        warnings = [f"Some document parts could not be checked ({_short_error(exc)})."]
    unread_paragraphs = 0
    unread_tables = 0
    unread_pictures = 0
    first_error = ""

    def add_pictures(element) -> None:
        nonlocal unread_pictures
        pictures, unread = _pictures(document, element)
        unread_pictures += unread
        for picture in pictures:
            block_id = block_id_for(len(blocks) + 1)
            alt = _markdown_alt(picture.alt or "Figure")
            start, end, end_column = preview.add(f"![{alt}]({FIGURE_LINK_SCHEME}{block_id})")
            blocks.append(
                OfficeBlock(
                    parsed=ParsedBlock(
                        page_number=1,
                        block_type="image",
                        text="",
                        image_bytes=picture.data,
                        image_ext=picture.ext,
                    ),
                    region=text_span(start, end, end_column),
                )
            )

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
                if text:
                    level = _heading_level(item)
                    if level is not None:
                        add("heading", text, heading_level=level, markdown=f"{'#' * level} {text}")
                    elif _is_list(item):
                        add("list", text, markdown=f"- {text}")
                    else:
                        add("paragraph", text, markdown=text)
                add_pictures(item._p)
            else:
                rows = _table_rows(item)
                rendered = gfm_table(rows)
                if rendered.strip():
                    add("table", rendered, markdown=rendered)
                add_pictures(item._tbl)
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
    if unread_pictures:
        plural = "s were" if unread_pictures != 1 else " was"
        warnings.append(
            f"{unread_pictures} linked or unreadable picture{plural} left out of figures."
        )
    body = preview.text()
    page = ParsedPage(page_number=1, width=None, height=None, text=body)
    return [page], blocks, body, warnings, notes
