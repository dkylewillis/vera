from __future__ import annotations

import re
from dataclasses import dataclass, field

from .parsers import ParsedBlock

_HEADING_RE = re.compile(r"^(chapter|section|article|part|appendix|stormwater|zoning|[0-9]+(?:\.[0-9]+)*)\b", re.I)


@dataclass
class Chunk:
    text: str
    page_start: int
    page_end: int
    heading_path: str
    token_count: int
    block_ids: list[str] = field(default_factory=list)


def tokens(text: str) -> list[str]:
    return text.split()


def detect_heading(text: str, current: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and len(stripped) < 120 and _HEADING_RE.match(stripped):
            return stripped
    return current


def chunk_pages(pages, chunk_size: int = 500, overlap: int = 75) -> list[Chunk]:
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
                    chunks.append(Chunk(text, page.page_number, page.page_number, heading, len(tokens(text))))
                    buffer = []
                step = chunk_size - overlap
                for start in range(0, len(words), step):
                    part = words[start : start + chunk_size]
                    if part:
                        chunks.append(Chunk(" ".join(part), page.page_number, page.page_number, heading, len(part)))
                    if start + chunk_size >= len(words):
                        break
            elif len(buffer) + len(words) > chunk_size and buffer:
                text = " ".join(buffer)
                chunks.append(Chunk(text, page.page_number, page.page_number, heading, len(tokens(text))))
                buffer = buffer[-overlap:] if overlap else []
                buffer.extend(words)
            else:
                buffer.extend(words)
        if buffer:
            text = " ".join(buffer)
            chunks.append(Chunk(text, page.page_number, page.page_number, heading, len(tokens(text))))
    return chunks


def build_chunks_from_blocks(
    blocks: list[tuple[str, ParsedBlock]],
    chunk_size: int = 500,
    overlap: int = 75,
) -> list[Chunk]:
    """Heading-aware chunking over structured blocks."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    overlap = max(0, min(overlap, chunk_size - 1))

    chunks: list[Chunk] = []
    heading_stack: list[tuple[int, str]] = []
    buffer_words: list[str] = []
    buffer_blocks: list[str] = []
    buffer_pages: list[int] = []

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

    for block_id, block in blocks:
        if block.block_type == "image":
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
        words = tokens(block.text)
        if not words:
            continue
        if len(words) > chunk_size:
            flush()
            step = chunk_size - overlap
            for start in range(0, len(words), step):
                part = words[start : start + chunk_size]
                if part:
                    chunks.append(
                        Chunk(
                            " ".join(part),
                            block.page_number,
                            block.page_number,
                            heading_path(),
                            len(part),
                            [block_id],
                        )
                    )
                if start + chunk_size >= len(words):
                    break
            continue
        if buffer_words and len(buffer_words) + len(words) > chunk_size:
            carry = buffer_words[-overlap:] if overlap else []
            flush()
            buffer_words.extend(carry)
        buffer_words.extend(words)
        buffer_blocks.append(block_id)
        buffer_pages.append(block.page_number)
    flush()
    return chunks
