from __future__ import annotations

import hashlib
import json
import mimetypes
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .core.embeddings import get_embedder, serialize_vector
from .core.schema import FORMAT_VERSION, create_schema
from .ingest.chunking import build_chunks_from_blocks
from .ingest.parsers import ParsedBlock, parse_pdf_structured


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _drop_repeated_images(
    block_records: list[tuple[str, ParsedBlock]],
) -> list[tuple[str, ParsedBlock]]:
    """Keep only the first occurrence of each distinct image in the document.

    A logo or letterhead mark repeated on every page would otherwise be stored
    (and surfaced as a "figure") once per page. Keeping just the first
    occurrence avoids that storage bloat and search-result noise while still
    preserving genuinely distinct images.
    """
    seen_hashes: set[str] = set()
    kept: list[tuple[str, ParsedBlock]] = []
    for block_id, block in block_records:
        if block.block_type == "image" and block.image_bytes:
            image_hash = _sha256_bytes(block.image_bytes)
            if image_hash in seen_hashes:
                continue
            seen_hashes.add(image_hash)
        kept.append((block_id, block))
    return kept


def convert(
    input_path: str,
    output_path: str,
    *,
    model: str = "hashing",
    parser: str = "pymupdf",
    chunk_size: int = 500,
    overlap: int = 75,
    store_original: bool = True,
) -> str:
    source = Path(input_path)
    target = Path(output_path)
    if not source.exists():
        raise FileNotFoundError(input_path)
    if parser != "pymupdf":
        raise ValueError("v0.1 currently supports parser='pymupdf'")

    source_data = source.read_bytes()
    source_hash = _sha256_bytes(source_data)
    mime_type = mimetypes.guess_type(source.name)[0] or "application/pdf"
    pages, parsed_blocks = parse_pdf_structured(str(source))
    block_records: list[tuple[str, ParsedBlock]] = [
        (f"block_{idx:06d}", block) for idx, block in enumerate(parsed_blocks, start=1)
    ]
    block_records = _drop_repeated_images(block_records)
    chunks = build_chunks_from_blocks(block_records, chunk_size=chunk_size, overlap=overlap)
    embedder = get_embedder(model)
    vectors = embedder.embed([c.text for c in chunks]) if chunks else []

    if target.exists():
        target.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    try:
        create_schema(conn)
        now = _utc_now()
        doc_id = "doc_001"
        metadata = {
            "format_name": "VERA",
            "format_version": FORMAT_VERSION,
            "created_at": now,
            "created_by": "vera",
            "creator_library": "vera-python/0.1.0",
            "source_file_name": source.name,
            "source_file_hash": source_hash,
            "source_mime_type": mime_type,
            "default_embedding_model": embedder.model_name,
            "default_embedding_dimension": str(embedder.dimension),
            "chunking_strategy": f"heading_block_sliding_window:{chunk_size}:{overlap}",
            "parser_name": parser,
            "parser_version": "pymupdf",
        }
        conn.executemany("INSERT INTO vera_metadata(key, value) VALUES (?, ?)", metadata.items())
        conn.execute(
            "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?)",
            (doc_id, source.stem, source.name, mime_type, source_hash, len(pages), now),
        )
        for page in pages:
            page_id = f"page_{page.page_number:06d}"
            conn.execute(
                "INSERT INTO pages VALUES (?, ?, ?, ?, ?, ?)",
                (page_id, doc_id, page.page_number, page.width, page.height, page.text),
            )
        for sort_order, (block_id, block) in enumerate(block_records, start=1):
            page_id = f"page_{block.page_number:06d}"
            bbox_json = json.dumps(list(block.bbox)) if block.bbox else None
            conn.execute(
                "INSERT INTO blocks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    block_id,
                    doc_id,
                    page_id,
                    block.page_number,
                    block.block_type,
                    block.text,
                    bbox_json,
                    block.heading_level,
                    sort_order,
                ),
            )
            if block.block_type == "image" and block.image_bytes:
                ext = block.image_ext or "png"
                conn.execute(
                    "INSERT INTO assets VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        f"asset_{block_id}",
                        doc_id,
                        "extracted_image",
                        f"image/{ext}",
                        f"page{block.page_number:04d}_{block_id}.{ext}",
                        block.image_bytes,
                        _sha256_bytes(block.image_bytes),
                    ),
                )
        for idx, (chunk, vector) in enumerate(zip(chunks, vectors), start=1):
            chunk_id = f"chunk_{idx:06d}"
            text_hash = hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()
            conn.execute(
                "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (chunk_id, doc_id, chunk.page_start, chunk.page_end, chunk.heading_path, chunk.text, chunk.token_count, text_hash, idx),
            )
            conn.executemany(
                "INSERT OR IGNORE INTO chunk_blocks(chunk_id, block_id) VALUES (?, ?)",
                [(chunk_id, block_id) for block_id in chunk.block_ids],
            )
            conn.execute("INSERT INTO chunks_fts(chunk_id, text, heading_path) VALUES (?, ?, ?)", (chunk_id, chunk.text, chunk.heading_path))
            conn.execute(
                "INSERT INTO embeddings VALUES (?, ?, ?, ?, ?, ?, ?)",
                (f"emb_{idx:06d}", chunk_id, embedder.model_name, embedder.dimension, serialize_vector(vector), "float32_le", now),
            )
        if store_original:
            conn.execute(
                "INSERT INTO assets VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("asset_original_001", doc_id, "original_document", mime_type, source.name, source_data, source_hash),
            )
        conn.commit()
    finally:
        conn.close()
    return str(target)
