"""Layout and convert-invariant lint for lab documents."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from vera_ingest.types import IngestResult
from vera_lab.model import LabDocument


@dataclass(frozen=True)
class LabIssue:
    """One lint finding."""

    code: str
    severity: str  # "error" | "warning"
    message: str
    subject_id: str | None = None
    page_number: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def lint_ingest_result(result: IngestResult) -> list[LabIssue]:
    """Report convert-invariant violations without raising on the first one."""
    issues: list[LabIssue] = []
    block_ids = [block.block_id for block in result.blocks]
    chunk_ids = [chunk.chunk_id for chunk in result.chunks]

    for block_id in block_ids:
        if not block_id.strip():
            issues.append(
                LabIssue(
                    code="empty_block_id",
                    severity="error",
                    message="Ingest pipeline produced an empty block ID",
                    subject_id=block_id or None,
                )
            )
    if len(block_ids) != len(set(block_ids)):
        seen: set[str] = set()
        for block_id in block_ids:
            if block_id in seen:
                issues.append(
                    LabIssue(
                        code="duplicate_block_id",
                        severity="error",
                        message=f"Duplicate block ID {block_id!r}",
                        subject_id=block_id,
                    )
                )
            seen.add(block_id)

    for chunk_id in chunk_ids:
        if not chunk_id.strip():
            issues.append(
                LabIssue(
                    code="empty_chunk_id",
                    severity="error",
                    message="Ingest pipeline produced an empty chunk ID",
                    subject_id=chunk_id or None,
                )
            )
    if len(chunk_ids) != len(set(chunk_ids)):
        seen_chunks: set[str] = set()
        for chunk_id in chunk_ids:
            if chunk_id in seen_chunks:
                issues.append(
                    LabIssue(
                        code="duplicate_chunk_id",
                        severity="error",
                        message=f"Duplicate chunk ID {chunk_id!r}",
                        subject_id=chunk_id,
                    )
                )
            seen_chunks.add(chunk_id)

    known_blocks = set(block_ids)
    for chunk in result.chunks:
        unknown = set(chunk.block_ids) - known_blocks
        if unknown:
            names = ", ".join(sorted(unknown))
            issues.append(
                LabIssue(
                    code="unknown_block_ids",
                    severity="error",
                    message=(
                        f"Ingest chunk {chunk.chunk_id!r} references unknown block IDs: {names}"
                    ),
                    subject_id=chunk.chunk_id,
                    page_number=chunk.page_start,
                )
            )
        if not chunk.text.strip():
            issues.append(
                LabIssue(
                    code="empty_chunk_text",
                    severity="error",
                    message=f"Ingest chunk {chunk.chunk_id!r} has no readable text",
                    subject_id=chunk.chunk_id,
                    page_number=chunk.page_start,
                )
            )
    return issues


def lint_document(document: LabDocument) -> list[LabIssue]:
    """Run convert invariants (when reconstructible) plus layout lint."""
    issues: list[LabIssue] = []
    issues.extend(_lint_ids_from_document(document))
    issues.extend(_lint_layout(document))
    return issues


def _lint_ids_from_document(document: LabDocument) -> list[LabIssue]:
    """Mirror convert invariants against the lab view model."""
    issues: list[LabIssue] = []
    block_ids = [block.block_id for block in document.blocks]
    chunk_ids = [chunk.chunk_id for chunk in document.chunks]

    for block_id in block_ids:
        if not str(block_id).strip():
            issues.append(
                LabIssue(
                    code="empty_block_id",
                    severity="error",
                    message="Ingest pipeline produced an empty block ID",
                )
            )
    if len(block_ids) != len(set(block_ids)):
        seen: set[str] = set()
        for block_id in block_ids:
            if block_id in seen:
                issues.append(
                    LabIssue(
                        code="duplicate_block_id",
                        severity="error",
                        message=f"Duplicate block ID {block_id!r}",
                        subject_id=block_id,
                    )
                )
            seen.add(block_id)

    for chunk_id in chunk_ids:
        if not str(chunk_id).strip():
            issues.append(
                LabIssue(
                    code="empty_chunk_id",
                    severity="error",
                    message="Ingest pipeline produced an empty chunk ID",
                )
            )
    if len(chunk_ids) != len(set(chunk_ids)):
        seen_chunks: set[str] = set()
        for chunk_id in chunk_ids:
            if chunk_id in seen_chunks:
                issues.append(
                    LabIssue(
                        code="duplicate_chunk_id",
                        severity="error",
                        message=f"Duplicate chunk ID {chunk_id!r}",
                        subject_id=chunk_id,
                    )
                )
            seen_chunks.add(chunk_id)

    known_blocks = set(block_ids)
    for chunk in document.chunks:
        unknown = set(chunk.block_ids) - known_blocks
        if unknown:
            names = ", ".join(sorted(unknown))
            issues.append(
                LabIssue(
                    code="unknown_block_ids",
                    severity="error",
                    message=(
                        f"Ingest chunk {chunk.chunk_id!r} references unknown block IDs: {names}"
                    ),
                    subject_id=chunk.chunk_id,
                    page_number=chunk.page_start,
                )
            )
        if not chunk.text.strip():
            issues.append(
                LabIssue(
                    code="empty_chunk_text",
                    severity="error",
                    message=f"Ingest chunk {chunk.chunk_id!r} has no readable text",
                    subject_id=chunk.chunk_id,
                    page_number=chunk.page_start,
                )
            )
    return issues


def _lint_layout(document: LabDocument) -> list[LabIssue]:
    issues: list[LabIssue] = []
    covered_block_ids: set[str] = set()
    for chunk in document.chunks:
        covered_block_ids.update(chunk.block_ids)
        if chunk.page_start != chunk.page_end:
            issues.append(
                LabIssue(
                    code="cross_page_chunk",
                    severity="warning",
                    message=(
                        f"Chunk {chunk.chunk_id!r} spans pages {chunk.page_start}-{chunk.page_end}"
                    ),
                    subject_id=chunk.chunk_id,
                    page_number=chunk.page_start,
                )
            )

    figure_pages = {figure.page_number for figure in document.figures}

    for block in document.blocks:
        if block.block_id not in covered_block_ids:
            if block.block_type == "image":
                issues.append(
                    LabIssue(
                        code="unlinked_image_block",
                        severity="warning",
                        message=(
                            f"Image block {block.block_id!r} is not linked to any chunk; "
                            "figures will be omitted from --figures"
                        ),
                        subject_id=block.block_id,
                        page_number=block.page_number,
                    )
                )
            elif block.block_type == "heading":
                # Headings are often used only for heading_path, not chunk text.
                pass
            elif block.block_type == "table":
                issues.append(
                    LabIssue(
                        code="orphan_table_text",
                        severity="warning",
                        message=(f"Table block {block.block_id!r} is not referenced by any chunk"),
                        subject_id=block.block_id,
                        page_number=block.page_number,
                    )
                )
            else:
                issues.append(
                    LabIssue(
                        code="uncovered_block",
                        severity="warning",
                        message=(
                            f"Block {block.block_id!r} ({block.block_type}) is not "
                            "referenced by any chunk"
                        ),
                        subject_id=block.block_id,
                        page_number=block.page_number,
                    )
                )

        if (
            block.block_type not in {"image", "heading"}
            and block.bbox is None
            and block.block_id in covered_block_ids
        ):
            issues.append(
                LabIssue(
                    code="missing_bbox",
                    severity="warning",
                    message=(
                        f"Text block {block.block_id!r} has no bbox; "
                        "its chunk will have no highlight region"
                    ),
                    subject_id=block.block_id,
                    page_number=block.page_number,
                )
            )

        if block.bbox is not None and len(block.bbox) == 4:
            x0, y0, x1, y1 = (float(v) for v in block.bbox)
            if x1 <= x0 or y1 <= y0:
                issues.append(
                    LabIssue(
                        code="degenerate_bbox",
                        severity="warning",
                        message=f"Block {block.block_id!r} has a zero-area or inverted bbox",
                        subject_id=block.block_id,
                        page_number=block.page_number,
                    )
                )

        if block.block_type == "caption":
            page_has_figure = block.page_number in figure_pages or any(
                b.block_type == "image" and b.page_number == block.page_number
                for b in document.blocks
            )
            if not page_has_figure:
                issues.append(
                    LabIssue(
                        code="caption_without_figure",
                        severity="warning",
                        message=(
                            f"Caption block {block.block_id!r} has no figure on page "
                            f"{block.page_number}"
                        ),
                        subject_id=block.block_id,
                        page_number=block.page_number,
                    )
                )

    # Overlapping same-type bboxes on the same page (heavy overlap).
    by_page: dict[int, list[Any]] = {}
    for block in document.blocks:
        if block.bbox is None or len(block.bbox) != 4:
            continue
        by_page.setdefault(block.page_number, []).append(block)
    for page_number, page_blocks in by_page.items():
        for index, left in enumerate(page_blocks):
            for right in page_blocks[index + 1 :]:
                if left.block_type != right.block_type:
                    continue
                if _overlap_ratio(left.bbox, right.bbox) >= 0.8:
                    issues.append(
                        LabIssue(
                            code="overlapping_bboxes",
                            severity="warning",
                            message=(
                                f"Blocks {left.block_id!r} and {right.block_id!r} "
                                f"overlap heavily on page {page_number}"
                            ),
                            subject_id=left.block_id,
                            page_number=page_number,
                        )
                    )

    return issues


def _overlap_ratio(a: list[float], b: list[float]) -> float:
    ax0, ay0, ax1, ay1 = (float(v) for v in a)
    bx0, by0, bx1, by1 = (float(v) for v in b)
    ix0 = max(ax0, bx0)
    iy0 = max(ay0, by0)
    ix1 = min(ax1, bx1)
    iy1 = min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    intersection = (ix1 - ix0) * (iy1 - iy0)
    area_a = max(0.0, (ax1 - ax0) * (ay1 - ay0))
    area_b = max(0.0, (bx1 - bx0) * (by1 - by0))
    smaller = min(area_a, area_b)
    if smaller <= 0:
        return 0.0
    return intersection / smaller
