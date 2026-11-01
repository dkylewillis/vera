"""Dispatch Word, PowerPoint, and Excel sources through one OOXML pipeline."""

from __future__ import annotations

import json
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from vera_ingest.chunking import build_chunks_from_blocks
from vera_ingest.formats import source_suffix
from vera_ingest.types import (
    IngestBlock,
    IngestChunk,
    IngestPreview,
    IngestRequest,
    IngestResult,
    ensure_ingest_request,
)

from .common import OfficeBlock, block_id_for, sheet_citation
from .docx import parse_docx
from .options import OoxmlOptions
from .pptx import parse_pptx
from .xlsx import parse_xlsx


def _package_version() -> str:
    try:
        return version("vera-ingest-ooxml")
    except PackageNotFoundError:  # pragma: no cover - editable/source runs
        return "unknown"


def _assign_ids(blocks: list[OfficeBlock]) -> list[tuple[str, IngestBlock]]:
    records: list[tuple[str, IngestBlock]] = []
    for index, item in enumerate(blocks, start=1):
        block_id = block_id_for(index)
        region = {**item.region, "block_id": block_id}
        records.append(
            (
                block_id,
                IngestBlock.from_parsed(block_id, item.parsed, regions=[region]),
            )
        )
    return records


def _slide_label(block_ids: list[str], by_id: dict[str, IngestBlock]) -> str:
    slides: list[int] = []
    for block_id in block_ids:
        block = by_id.get(block_id)
        if block is None:
            continue
        for region in block.regions:
            if region.get("kind") == "slide" and isinstance(region.get("slide"), int):
                slides.append(int(region["slide"]))
    if not slides:
        return ""
    start, end = min(slides), max(slides)
    return f"slide {start}" if start == end else f"slides {start}-{end}"


def _chunks_for_slides(
    records: list[tuple[str, IngestBlock]],
    *,
    chunk_size: int,
    overlap: int,
) -> list[IngestChunk]:
    by_id = dict(records)
    chunks: list[IngestChunk] = []
    for index, chunk in enumerate(
        build_chunks_from_blocks(records, chunk_size=chunk_size, overlap=overlap),
        start=1,
    ):
        label = _slide_label(chunk.block_ids, by_id)
        chunks.append(
            IngestChunk(
                chunk_id=f"chunk_{index:06d}",
                text=chunk.text,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                heading_path=chunk.heading_path,
                token_count=chunk.token_count,
                block_ids=list(chunk.block_ids),
                metadata={"citation_label": label} if label else {},
            )
        )
    return chunks


def _chunks_for_sheets(records: list[tuple[str, IngestBlock]]) -> list[IngestChunk]:
    """One chunk per row-group table. Tables are never split mid-row."""
    heading = ""
    chunks: list[IngestChunk] = []
    for block_id, block in records:
        if block.block_type == "heading":
            heading = block.text
            continue
        if block.block_type != "table" or not block.text.strip():
            continue
        label = ""
        for region in block.regions:
            if region.get("kind") == "sheet_range":
                sheet = str(region.get("sheet") or "")
                cell_range = str(region.get("range") or "")
                if sheet and cell_range:
                    label = sheet_citation(sheet, cell_range)
        chunks.append(
            IngestChunk(
                chunk_id=f"chunk_{len(chunks) + 1:06d}",
                text=block.text,
                page_start=block.page_number,
                page_end=block.page_number,
                heading_path=heading,
                token_count=len(block.text.split()),
                block_ids=[block_id],
                metadata={"citation_label": label} if label else {},
            )
        )
    return chunks


def _chunks_for_words(
    records: list[tuple[str, IngestBlock]],
    *,
    chunk_size: int,
    overlap: int,
) -> list[IngestChunk]:
    return [
        IngestChunk(
            chunk_id=f"chunk_{index:06d}",
            text=chunk.text,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            heading_path=chunk.heading_path,
            token_count=chunk.token_count,
            block_ids=list(chunk.block_ids),
        )
        for index, chunk in enumerate(
            build_chunks_from_blocks(records, chunk_size=chunk_size, overlap=overlap),
            start=1,
        )
    ]


def _slide_preview(records: list[tuple[str, IngestBlock]]) -> bytes:
    slides: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for block_id, block in records:
        if current is None or current["slide"] != block.page_number:
            current = {"slide": block.page_number, "blocks": []}
            slides.append(current)
        blocks = current["blocks"]
        assert isinstance(blocks, list)
        blocks.append(
            {
                "block_id": block_id,
                "kind": block.block_type,
                "text": block.text,
            }
        )
    return json.dumps({"slides": slides}, ensure_ascii=False).encode("utf-8")


def ooxml_pipeline(source_path: str, options: IngestRequest) -> IngestResult:
    """Ingest a ``.docx``, ``.pptx``, or ``.xlsx`` file."""
    request = ensure_ingest_request(options)
    config = OoxmlOptions.from_mapping(request.pipeline_options)
    suffix = source_suffix(source_path)
    source_name = Path(source_path).name
    warnings: list[str] = []
    notes: list[str] = []
    if suffix == "docx":
        pages, office_blocks, preview_text, warnings, notes = parse_docx(source_path)
        records = _assign_ids(office_blocks)
        chunks = _chunks_for_words(records, chunk_size=config.chunk_size, overlap=config.overlap)
        preview = IngestPreview(
            media_type="text/markdown",
            filename=f"{Path(source_name).stem}.md",
            data=preview_text.encode("utf-8"),
        )
        strategy = f"ooxml_docx_heading_block:{config.chunk_size}:{config.overlap}"
    elif suffix == "pptx":
        pages, office_blocks = parse_pptx(source_path, include_notes=config.include_notes)
        records = _assign_ids(office_blocks)
        chunks = _chunks_for_slides(records, chunk_size=config.chunk_size, overlap=config.overlap)
        preview = IngestPreview(
            media_type="application/vnd.vera.slides+json",
            filename=f"{Path(source_name).stem}.slides.json",
            data=_slide_preview(records),
        )
        strategy = f"ooxml_pptx_slide:{config.chunk_size}:{config.overlap}"
    elif suffix == "xlsx":
        pages, office_blocks, sheet_preview = parse_xlsx(
            source_path,
            rows_per_chunk=config.rows_per_chunk,
        )
        records = _assign_ids(office_blocks)
        chunks = _chunks_for_sheets(records)
        preview = IngestPreview(
            media_type="application/vnd.vera.sheets+json",
            filename=f"{Path(source_name).stem}.sheets.json",
            data=json.dumps(sheet_preview, ensure_ascii=False).encode("utf-8"),
        )
        strategy = f"ooxml_xlsx_rows:{config.rows_per_chunk}"
    else:
        raise ValueError(
            f"OOXML pipeline does not support {Path(source_path).suffix or 'extensionless'} files "
            "(supports: .docx, .pptx, .xlsx)."
        )
    return IngestResult(
        pages=pages,
        blocks=[block for _, block in records],
        chunks=chunks,
        parser_name="ooxml",
        parser_version=_package_version(),
        chunking_strategy=strategy,
        viewer_preview=preview,
        warnings=warnings,
        notes=notes,
    )
