from __future__ import annotations

import re
from dataclasses import dataclass, field

from .types import IngestBlock, ParsedBlock, ParsedPage

_HEADING_RE = re.compile(
    r"^(chapter|section|article|part|appendix|stormwater|zoning|[0-9]+(?:\.[0-9]+)*)\b", re.I
)


@dataclass
class Chunk:
    """Text segment produced by the extraction chunker.

    Attributes:
        text: Chunk content.
        page_start: First page number spanned by the chunk.
        page_end: Last page number spanned by the chunk.
        heading_path: Heading breadcrumb at chunk start.
        token_count: Whitespace-split word count.
        block_ids: Source layout block identifiers.
    """

    text: str
    page_start: int
    page_end: int
    heading_path: str
    token_count: int
    block_ids: list[str] = field(default_factory=list)


def tokens(text: str) -> list[str]:
    """Split on whitespace. Chunk size and overlap count these words."""
    return text.split()


def detect_heading(text: str, current: str) -> str:
    """Return the first short heading-like line in ``text``, else ``current``.

    Public helper for custom pipelines that chunk page text with
    :func:`chunk_pages`. First-party pipelines use structured heading blocks
    via :func:`build_chunks_from_blocks` instead.
    """
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and len(stripped) < 120 and _HEADING_RE.match(stripped):
            return stripped
    return current


def _take_overflow_windows(
    buffer: list[str], chunk_size: int, overlap: int
) -> tuple[list[list[str]], list[str]]:
    """Emit ``chunk_size`` windows while ``buffer`` is oversized; keep remainder.

    After overlap carry plus a new paragraph, the combined buffer can exceed
    ``chunk_size``. Each emitted window is exactly ``chunk_size`` tokens; the
    remainder is always ``<= chunk_size``.
    """
    windows: list[list[str]] = []
    while len(buffer) > chunk_size:
        windows.append(buffer[:chunk_size])
        carry = buffer[chunk_size - overlap : chunk_size] if overlap else []
        buffer = carry + buffer[chunk_size:]
    return windows, buffer


def chunk_pages(pages: list[ParsedPage], chunk_size: int = 500, overlap: int = 75) -> list[Chunk]:
    """Sliding-window chunker over ``ParsedPage.text`` (whitespace-split words).

    Public helper for custom pipelines that only have page text. First-party
    pipelines (PyMuPDF, Docling) do not call this; they chunk structured
    layout with :func:`build_chunks_from_blocks` or their own chunker.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    overlap = max(0, min(overlap, chunk_size - 1))
    chunks: list[Chunk] = []
    heading = ""
    for page in pages:
        heading = detect_heading(page.text, heading)
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n|(?<=\.)\s*\n", page.text) if p.strip()]
        if not paragraphs and page.text.strip():
            paragraphs = [page.text.strip()]
        buffer: list[str] = []
        for para in paragraphs:
            words = tokens(para)
            if len(words) > chunk_size:
                if buffer:
                    text = " ".join(buffer)
                    chunks.append(
                        Chunk(text, page.page_number, page.page_number, heading, len(tokens(text)))
                    )
                    buffer = []
                step = chunk_size - overlap
                for start in range(0, len(words), step):
                    part = words[start : start + chunk_size]
                    if part:
                        chunks.append(
                            Chunk(
                                " ".join(part),
                                page.page_number,
                                page.page_number,
                                heading,
                                len(part),
                            )
                        )
                    if start + chunk_size >= len(words):
                        break
            elif len(buffer) + len(words) > chunk_size and buffer:
                text = " ".join(buffer)
                chunks.append(
                    Chunk(text, page.page_number, page.page_number, heading, len(tokens(text)))
                )
                buffer = buffer[-overlap:] if overlap else []
                buffer.extend(words)
                overflow, buffer = _take_overflow_windows(buffer, chunk_size, overlap)
                for window in overflow:
                    chunks.append(
                        Chunk(
                            " ".join(window),
                            page.page_number,
                            page.page_number,
                            heading,
                            len(window),
                        )
                    )
            else:
                buffer.extend(words)
        if buffer:
            text = " ".join(buffer)
            chunks.append(
                Chunk(text, page.page_number, page.page_number, heading, len(tokens(text)))
            )
    return chunks


def build_chunks_from_blocks(
    blocks: list[tuple[str, ParsedBlock | IngestBlock]],
    chunk_size: int = 500,
    overlap: int = 75,
) -> list[Chunk]:
    """Heading-aware chunking over structured layout blocks.

    Accepts ``(block_id, block)`` pairs of either :class:`ParsedBlock` or
    :class:`IngestBlock`. First-party PyMuPDF uses this path; custom pipelines
    that only have page text should use :func:`chunk_pages` instead.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    overlap = max(0, min(overlap, chunk_size - 1))

    chunks: list[Chunk] = []
    heading_stack: list[tuple[int, str]] = []
    buffer_words: list[str] = []
    buffer_blocks: list[str] = []
    buffer_pages: list[int] = []
    # Image block ids seen since the last flush that haven't yet been attached
    # to a chunk (e.g. an image appears before any text on a fresh page).
    pending_images: list[tuple[int, str]] = []

    def heading_path() -> str:
        return " > ".join(text for _, text in heading_stack)

    def flush() -> None:
        nonlocal buffer_words, buffer_blocks, buffer_pages
        if buffer_words:
            text = " ".join(buffer_words)
            chunks.append(
                Chunk(
                    text,
                    min(buffer_pages),
                    max(buffer_pages),
                    heading_path(),
                    len(buffer_words),
                    list(dict.fromkeys(buffer_blocks)),
                )
            )
        buffer_words = []
        buffer_blocks = []
        buffer_pages = []

    def attach_pending_images(page_number: int, target_block_ids: list[str]) -> None:
        """Attach queued image block ids for this page onto a chunk's blocks."""
        nonlocal pending_images
        if not pending_images:
            return
        remaining = []
        for pg, image_block_id in pending_images:
            if pg == page_number:
                target_block_ids.append(image_block_id)
            else:
                remaining.append((pg, image_block_id))
        pending_images = remaining

    for block_id, block in blocks:
        if block.block_type == "image":
            if buffer_words and buffer_pages and buffer_pages[-1] == block.page_number:
                # A chunk is actively being assembled for this page — attach directly
                # so the image travels with its surrounding text.
                buffer_blocks.append(block_id)
            else:
                # No open chunk on this page yet — queue it for the next one.
                pending_images.append((block.page_number, block_id))
            continue
        if buffer_pages and block.page_number != buffer_pages[-1]:
            # Keep citations page-precise: do not merge chunks across pages.
            flush()
        if block.block_type == "heading":
            flush()
            level = block.heading_level or 6
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, block.text))
            continue
        if block.block_type == "table":
            flush()
        words = tokens(block.text)
        if not words:
            continue
        if len(words) > chunk_size:
            flush()
            step = chunk_size - overlap
            first_part = True
            for start in range(0, len(words), step):
                part = words[start : start + chunk_size]
                if part:
                    part_block_ids = [block_id]
                    if first_part:
                        attach_pending_images(block.page_number, part_block_ids)
                        first_part = False
                    chunks.append(
                        Chunk(
                            " ".join(part),
                            block.page_number,
                            block.page_number,
                            heading_path(),
                            len(part),
                            part_block_ids,
                        )
                    )
                if start + chunk_size >= len(words):
                    break
            continue
        if buffer_words and len(buffer_words) + len(words) > chunk_size:
            carry = buffer_words[-overlap:] if overlap else []
            flush()
            buffer_words.extend(carry)
        starting_new_buffer = not buffer_words
        buffer_words.extend(words)
        buffer_blocks.append(block_id)
        buffer_pages.append(block.page_number)
        if starting_new_buffer:
            attach_pending_images(block.page_number, buffer_blocks)
        overflow, buffer_words = _take_overflow_windows(buffer_words, chunk_size, overlap)
        for window in overflow:
            chunks.append(
                Chunk(
                    " ".join(window),
                    min(buffer_pages),
                    max(buffer_pages),
                    heading_path(),
                    len(window),
                    list(dict.fromkeys(buffer_blocks)),
                )
            )
    flush()
    if pending_images:
        # Trailing images with no following text on their page: attach to the
        # last chunk that already covers that page, if any.
        for page_number, image_block_id in pending_images:
            for chunk in reversed(chunks):
                if chunk.page_start <= page_number <= chunk.page_end:
                    chunk.block_ids.append(image_block_id)
                    break
    return chunks
