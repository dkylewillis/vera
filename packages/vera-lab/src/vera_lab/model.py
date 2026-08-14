"""Normalized view model shared by live and archive lab modes."""

from __future__ import annotations

import base64
from dataclasses import asdict, dataclass, field
from typing import Any

from vera_ingest.types import IngestBlock, IngestChunk, IngestResult


@dataclass
class LabRegion:
    """Highlight region for a chunk (page points, top-left origin)."""

    block_id: str
    page_number: int
    bbox: list[float]
    page_width: float | None = None
    page_height: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LabBlock:
    block_id: str
    page_number: int
    block_type: str
    text: str
    bbox: list[float] | None = None
    heading_level: int | None = None
    sort_order: int = 0
    has_image: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LabChunk:
    chunk_id: str
    text: str
    page_start: int
    page_end: int
    heading_path: str
    token_count: int
    block_ids: list[str] = field(default_factory=list)
    regions: list[LabRegion] = field(default_factory=list)
    embedding_text: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "text": self.text,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "heading_path": self.heading_path,
            "token_count": self.token_count,
            "block_ids": list(self.block_ids),
            "regions": [region.as_dict() for region in self.regions],
            "embedding_text": self.embedding_text,
        }


@dataclass
class LabFigure:
    block_id: str
    page_number: int
    bbox: list[float] | None
    page_width: float | None
    page_height: float | None
    mime_type: str | None = None
    filename: str | None = None
    caption: str | None = None
    data_url: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LabPage:
    page_number: int
    width: float | None
    height: float | None
    text: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LabDocument:
    """Normalized layout view for the HTML report."""

    source_path: str
    source_bytes: bytes
    pages: list[LabPage]
    blocks: list[LabBlock]
    chunks: list[LabChunk]
    figures: list[LabFigure]
    parser_name: str = ""
    parser_version: str = ""
    chunking_strategy: str = ""
    diagnostics: dict[str, Any] = field(default_factory=dict)
    pipeline_spec: str = ""
    pipeline_options: dict[str, Any] = field(default_factory=dict)
    mode: str = "live"

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "pages": [page.as_dict() for page in self.pages],
            "blocks": [block.as_dict() for block in self.blocks],
            "chunks": [chunk.as_dict() for chunk in self.chunks],
            "figures": [figure.as_dict() for figure in self.figures],
            "parser_name": self.parser_name,
            "parser_version": self.parser_version,
            "chunking_strategy": self.chunking_strategy,
            "diagnostics": dict(self.diagnostics),
            "pipeline_spec": self.pipeline_spec,
            "pipeline_options": dict(self.pipeline_options),
            "mode": self.mode,
            "page_count": len(self.pages),
            "block_count": len(self.blocks),
            "chunk_count": len(self.chunks),
            "figure_count": len(self.figures),
        }


def regions_for_chunk(
    chunk: IngestChunk | LabChunk,
    block_lookup: dict[str, IngestBlock | LabBlock],
    page_dimensions: dict[int, tuple[float | None, float | None]],
) -> list[LabRegion]:
    """Derive highlight regions the way shared convert does.

    Skip image blocks; prefer explicit ``block.regions``; fall back to the
    block bbox; stamp page width/height from ``page_dimensions``.
    """
    regions: list[LabRegion] = []
    block_ids = chunk.block_ids if isinstance(chunk, (IngestChunk, LabChunk)) else []
    for block_id in block_ids:
        block = block_lookup.get(block_id)
        if block is None:
            continue
        block_type = getattr(block, "block_type", None)
        if block_type == "image":
            continue
        explicit_regions = list(getattr(block, "regions", None) or [])
        bbox = getattr(block, "bbox", None)
        if not explicit_regions and bbox:
            explicit_regions = [
                {
                    "page_number": block.page_number,
                    "bbox": list(bbox),
                }
            ]
        for explicit in explicit_regions:
            page_number = int(explicit["page_number"])
            width, height = page_dimensions.get(page_number, (None, None))
            box = list(explicit["bbox"])
            regions.append(
                LabRegion(
                    block_id=block_id,
                    page_number=page_number,
                    bbox=box,
                    page_width=explicit.get("page_width", width),
                    page_height=explicit.get("page_height", height),
                )
            )
    return regions


def lab_document_from_ingest_result(
    result: IngestResult,
    *,
    source_path: str,
    source_bytes: bytes,
    pipeline_spec: str = "",
    pipeline_options: dict[str, Any] | None = None,
) -> LabDocument:
    """Build a :class:`LabDocument` from a live :class:`IngestResult`."""
    pages = [
        LabPage(
            page_number=page.page_number,
            width=page.width,
            height=page.height,
            text=page.text,
        )
        for page in result.pages
    ]
    page_dimensions = {page.page_number: (page.width, page.height) for page in result.pages}
    blocks: list[LabBlock] = []
    block_lookup: dict[str, IngestBlock] = {}
    for index, block in enumerate(result.blocks, start=1):
        block_lookup[block.block_id] = block
        blocks.append(
            LabBlock(
                block_id=block.block_id,
                page_number=block.page_number,
                block_type=block.block_type,
                text=block.text,
                bbox=list(block.bbox) if block.bbox else None,
                heading_level=block.heading_level,
                sort_order=index,
                has_image=bool(block.image_bytes),
            )
        )
    chunks = [
        LabChunk(
            chunk_id=chunk.chunk_id,
            text=chunk.text,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            heading_path=chunk.heading_path,
            token_count=chunk.token_count,
            block_ids=list(chunk.block_ids),
            regions=regions_for_chunk(chunk, block_lookup, page_dimensions),
            embedding_text=chunk.embedding_text,
        )
        for chunk in result.chunks
    ]
    figures: list[LabFigure] = []
    for block in result.blocks:
        if block.block_type != "image" or not block.image_bytes:
            continue
        width, height = page_dimensions.get(block.page_number, (None, None))
        extension = block.image_ext or "png"
        mime = f"image/{extension}"
        data_url = f"data:{mime};base64,{base64.b64encode(block.image_bytes).decode('ascii')}"
        figures.append(
            LabFigure(
                block_id=block.block_id,
                page_number=block.page_number,
                bbox=list(block.bbox) if block.bbox else None,
                page_width=width,
                page_height=height,
                mime_type=mime,
                filename=f"page{block.page_number:04d}_{block.block_id}.{extension}",
                caption=_caption_for_page(result.blocks, block.page_number, block.bbox),
                data_url=data_url,
            )
        )
    return LabDocument(
        source_path=source_path,
        source_bytes=source_bytes,
        pages=pages,
        blocks=blocks,
        chunks=chunks,
        figures=figures,
        parser_name=result.parser_name,
        parser_version=result.parser_version,
        chunking_strategy=result.chunking_strategy,
        diagnostics=dict(result.diagnostics),
        pipeline_spec=pipeline_spec,
        pipeline_options=dict(pipeline_options or {}),
        mode="live",
    )


def _caption_for_page(
    blocks: list[IngestBlock],
    page_number: int,
    bbox: tuple[float, float, float, float] | None,
) -> str | None:
    candidates = [
        block
        for block in blocks
        if block.block_type == "caption" and block.page_number == page_number
    ]
    if not candidates:
        return None
    if len(candidates) == 1 or bbox is None:
        return candidates[0].text
    figure_bottom = float(bbox[3])

    def sort_key(block: IngestBlock) -> tuple[float, float]:
        box = block.bbox
        if box is None or len(box) < 2:
            return (float("inf"), float("inf"))
        below = float(box[1]) - figure_bottom
        return (0.0 if below >= 0 else 1.0, abs(below))

    return min(candidates, key=sort_key).text
