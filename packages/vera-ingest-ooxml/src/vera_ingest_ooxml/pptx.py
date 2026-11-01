"""PowerPoint (.pptx) parser: one page per slide, plus optional speaker notes."""

from __future__ import annotations

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from vera_ingest.types import ParsedBlock, ParsedPage

from .common import OfficeBlock, gfm_table


def _title_shape(slide):
    try:
        return slide.shapes.title
    except (AttributeError, ValueError):
        return None


def _shape_text(shape) -> str:
    if not getattr(shape, "has_text_frame", False):
        return ""
    return "\n".join(paragraph.text.strip() for paragraph in shape.text_frame.paragraphs).strip()


def _table_rows(shape) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in shape.table.rows:
        rows.append([cell.text.strip().replace("\n", " ") for cell in row.cells])
    return rows


def _add_shape(blocks: list[OfficeBlock], slide_number: int, shape_index: int, shape, title_shape) -> None:
    if shape is title_shape:
        return
    shape_type = getattr(shape, "shape_type", None)
    if shape_type == MSO_SHAPE_TYPE.GROUP:
        for child in shape.shapes:
            _add_shape(blocks, slide_number, shape_index, child, title_shape)
        return
    region = {"kind": "slide", "slide": slide_number, "shape_index": shape_index}
    if shape_type == MSO_SHAPE_TYPE.PICTURE:
        image = shape.image
        blocks.append(
            OfficeBlock(
                parsed=ParsedBlock(
                    page_number=slide_number,
                    block_type="image",
                    text="",
                    image_bytes=image.blob,
                    image_ext=image.ext or "png",
                ),
                region=region,
            )
        )
        return
    if getattr(shape, "has_table", False):
        rendered = gfm_table(_table_rows(shape))
        if rendered.strip():
            blocks.append(
                OfficeBlock(
                    parsed=ParsedBlock(
                        page_number=slide_number,
                        block_type="table",
                        text=rendered,
                    ),
                    region=region,
                )
            )
        return
    text = _shape_text(shape)
    if text:
        blocks.append(
            OfficeBlock(
                parsed=ParsedBlock(
                    page_number=slide_number,
                    block_type="paragraph",
                    text=text,
                ),
                region=region,
            )
        )


def parse_pptx(
    source_path: str,
    *,
    include_notes: bool = True,
) -> tuple[list[ParsedPage], list[OfficeBlock]]:
    """Return one page per slide and the blocks on that slide."""
    presentation = Presentation(source_path)
    pages: list[ParsedPage] = []
    blocks: list[OfficeBlock] = []
    for slide_number, slide in enumerate(presentation.slides, start=1):
        title_shape = _title_shape(slide)
        title = _shape_text(title_shape) if title_shape is not None else ""
        slide_blocks: list[OfficeBlock] = []
        if title:
            slide_blocks.append(
                OfficeBlock(
                    parsed=ParsedBlock(
                        page_number=slide_number,
                        block_type="heading",
                        text=title,
                        heading_level=1,
                    ),
                    region={"kind": "slide", "slide": slide_number, "shape_index": 0},
                )
            )
        for shape_index, shape in enumerate(slide.shapes, start=1):
            _add_shape(slide_blocks, slide_number, shape_index, shape, title_shape)
        if include_notes and slide.has_notes_slide:
            notes = ""
            notes_frame = slide.notes_slide.notes_text_frame
            if notes_frame is not None:
                notes = notes_frame.text.strip()
            if notes:
                slide_blocks.append(
                    OfficeBlock(
                        parsed=ParsedBlock(
                            page_number=slide_number,
                            block_type="notes",
                            text=notes,
                        ),
                        region={"kind": "slide", "slide": slide_number, "shape_index": -1},
                    )
                )
        page_text = "\n".join(block.parsed.text for block in slide_blocks if block.parsed.text)
        pages.append(ParsedPage(page_number=slide_number, width=None, height=None, text=page_text))
        blocks.extend(slide_blocks)
    return pages, blocks
