from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import sqlite3
import tempfile
from pathlib import Path
from collections.abc import Callable
from typing import Any

from vera import (
    AttachmentRecord,
    AttachmentRef,
    ChunkRecord,
    VeraDocument,
)
from vera.core.validation import validate_document

from .ingest.chunking import build_chunks_from_blocks
from .ingest.parsers import ParsedBlock, parse_pdf_structured


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_output(path: Path) -> dict[str, Any]:
    try:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            report = validate_document(conn)
        finally:
            conn.close()
    except (OSError, sqlite3.Error) as exc:
        return {"ok": False, "issues": [f"Unable to validate VERA database: {exc}"]}

    return report


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


def _raise_if_cancelled(cancel: Any | None) -> None:
    if cancel is None:
        return
    interrupted = getattr(cancel, "raise_if_interrupted", None)
    if callable(interrupted):
        interrupted()
        return
    cancel.raise_if_cancelled()


def _consume_user_skip(cancel: Any | None, exc: BaseException) -> bool:
    """Clear a one-shot skip request if `exc` represents skipping the current file."""
    if cancel is None:
        return False
    if getattr(cancel, "cancelled", False):
        return False
    is_skip = type(exc).__name__ == "SkipCurrentError" or bool(
        getattr(cancel, "skip_requested", False)
    )
    if not is_skip:
        return False
    clear = getattr(cancel, "clear_skip", None)
    if callable(clear):
        clear()
    return True


def convert(
    input_path: str,
    output_path: str,
    *,
    model: str = "hashing",
    parser: str = "pymupdf",
    chunk_size: int = 500,
    overlap: int = 75,
    store_original: bool = True,
    ocr_mode: str = "auto",
    ocr_language: str = "eng",
    ocr_dpi: int = 300,
    cancel: Any | None = None,
) -> str:
    """Convert a PDF into a validated ``.vera`` archive.

    Parses the PDF, chunks extracted text, embeds chunks, and writes the
    result through :class:`~vera.document.VeraDocument`. The archive is
    validated before the temporary file is published atomically.

    Args:
        input_path: Source PDF path.
        output_path: Destination ``.vera`` path.
        model: Embedding model name (default ``"hashing"``).
        parser: PDF parser backend (currently only ``"pymupdf"``).
        chunk_size: Target chunk size in characters.
        overlap: Character overlap between consecutive chunks.
        store_original: When ``True``, embed the original PDF as an attachment.
        ocr_mode: ``"auto"`` (default), ``"off"``, or ``"force"``.
        ocr_language: Tesseract language code (default ``"eng"``).
        ocr_dpi: Rasterization DPI for OCR.
        cancel: Optional cancellation token with ``raise_if_cancelled()``.

    Returns:
        The ``output_path`` string.

    Raises:
        FileNotFoundError: When ``input_path`` does not exist.
        ValueError: When no searchable text is extracted or the parser is unsupported.
    """
    source = Path(input_path)
    target = Path(output_path)
    if not source.exists():
        raise FileNotFoundError(input_path)
    if parser != "pymupdf":
        raise ValueError("v0.1 currently supports parser='pymupdf'")

    _raise_if_cancelled(cancel)
    source_data = source.read_bytes()
    source_hash = _sha256_bytes(source_data)
    mime_type = mimetypes.guess_type(source.name)[0] or "application/pdf"
    parse_diagnostics: dict[str, Any] = {}
    pages, parsed_blocks = parse_pdf_structured(
        str(source),
        ocr_mode=ocr_mode,
        ocr_language=ocr_language,
        ocr_dpi=ocr_dpi,
        diagnostics=parse_diagnostics,
        cancel=cancel,
    )
    _raise_if_cancelled(cancel)
    block_records: list[tuple[str, ParsedBlock]] = [
        (f"block_{idx:06d}", block) for idx, block in enumerate(parsed_blocks, start=1)
    ]
    block_records = _drop_repeated_images(block_records)
    chunks = build_chunks_from_blocks(block_records, chunk_size=chunk_size, overlap=overlap)
    if not chunks:
        raise ValueError(
            "No searchable text or chunks were extracted; "
            "the PDF may be scanned and requires OCR."
        )
    _raise_if_cancelled(cancel)
    target.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
    )
    os.close(file_descriptor)
    temporary = Path(temporary_name)
    temporary.unlink()
    document: VeraDocument | None = None
    try:
        page_dimensions = {
            page.page_number: (page.width, page.height)
            for page in pages
        }
        page_payload = [
            {
                "page_number": page.page_number,
                "width": page.width,
                "height": page.height,
                "text": page.text,
            }
            for page in pages
        ]
        block_payload = [
            {
                "block_id": block_id,
                "page_number": block.page_number,
                "block_type": block.block_type,
                "text": block.text,
                "bbox": list(block.bbox) if block.bbox else None,
                "heading_level": block.heading_level,
                "sort_order": index,
            }
            for index, (block_id, block) in enumerate(block_records, start=1)
        ]
        block_lookup = dict(block_records)
        attachments: list[AttachmentRecord] = [
            AttachmentRecord(
                id="viewer_pages",
                media_type="application/vnd.vera.pages+json",
                filename="pages.json",
                data=json.dumps(page_payload, ensure_ascii=False).encode("utf-8"),
                metadata={"role": "viewer_pages"},
            ),
            AttachmentRecord(
                id="viewer_blocks",
                media_type="application/vnd.vera.blocks+json",
                filename="blocks.json",
                data=json.dumps(block_payload, ensure_ascii=False).encode("utf-8"),
                metadata={"role": "viewer_blocks"},
            ),
        ]
        image_attachment_by_block: dict[str, str] = {}
        for block_id, block in block_records:
            if block.block_type != "image" or not block.image_bytes:
                continue
            extension = block.image_ext or "png"
            attachment_id = f"image_{block_id}"
            image_attachment_by_block[block_id] = attachment_id
            attachments.append(
                AttachmentRecord(
                    id=attachment_id,
                    media_type=f"image/{extension}",
                    filename=f"page{block.page_number:04d}_{block_id}.{extension}",
                    data=block.image_bytes,
                    metadata={
                        "role": "figure",
                        "page_number": block.page_number,
                        "bbox": list(block.bbox) if block.bbox else None,
                    },
                )
            )
        source_attachment_id: str | None = None
        if store_original:
            source_attachment_id = "source_original"
            attachments.append(
                AttachmentRecord(
                    id=source_attachment_id,
                    media_type=mime_type,
                    filename=source.name,
                    data=source_data,
                    metadata={"role": "source"},
                )
            )

        archive_metadata = {
            "title": source.stem,
            "source_file_name": source.name,
            "source_file_hash": source_hash,
            "source_mime_type": mime_type,
            "chunking_strategy": f"heading_block_sliding_window:{chunk_size}:{overlap}",
            "parser_name": parser,
            "parser_version": "pymupdf",
            "ocr": parse_diagnostics,
            "page_count": len(pages),
            "viewer_pages_attachment_id": "viewer_pages",
            "viewer_blocks_attachment_id": "viewer_blocks",
            "source_attachment_id": source_attachment_id,
        }
        records: list[ChunkRecord] = []
        for index, chunk in enumerate(chunks, start=1):
            regions = []
            references: list[AttachmentRef] = []
            for block_id in chunk.block_ids:
                block = block_lookup.get(block_id)
                if block is None:
                    continue
                width, height = page_dimensions.get(
                    block.page_number,
                    (None, None),
                )
                if block.bbox and block.block_type != "image":
                    regions.append(
                        {
                            "block_id": block_id,
                            "page_number": block.page_number,
                            "bbox": list(block.bbox),
                            "page_width": width,
                            "page_height": height,
                        }
                    )
                image_attachment_id = image_attachment_by_block.get(block_id)
                if image_attachment_id:
                    references.append(
                        AttachmentRef(image_attachment_id, role="figure")
                    )
            if source_attachment_id:
                references.append(
                    AttachmentRef(source_attachment_id, role="source")
                )
            records.append(
                ChunkRecord(
                    id=f"chunk_{index:06d}",
                    text=chunk.text,
                    metadata={
                        "document_id": "document_0001",
                        "source_filename": source.name,
                        "page_start": chunk.page_start,
                        "page_end": chunk.page_end,
                        "heading_path": chunk.heading_path,
                        "token_count": chunk.token_count,
                        "regions": regions,
                    },
                    attachments=tuple(references),
                )
            )

        document = VeraDocument.create(
            temporary,
            model=model,
            metadata=archive_metadata,
        )
        with document.transaction():
            document.put_attachments(attachments)
            document.add(records)
        document.close()
        document = None
        _raise_if_cancelled(cancel)

        validation = _validate_output(temporary)
        if not validation["ok"]:
            issues = "; ".join(validation["issues"])
            raise ValueError(f"Converted VERA database failed validation: {issues}")

        os.replace(temporary, target)
    finally:
        if document is not None:
            document.close()
        temporary.unlink(missing_ok=True)
    return str(target)


def batch_convert(
    directory: str,
    *,
    recursive: bool = False,
    overwrite: bool = False,
    model: str = "hashing",
    parser: str = "pymupdf",
    chunk_size: int = 500,
    overlap: int = 75,
    store_original: bool = True,
    ocr_mode: str = "auto",
    ocr_language: str = "eng",
    ocr_dpi: int = 300,
    progress: Callable[[int, int, str], None] | None = None,
    cancel: Any | None = None,
) -> dict[str, Any]:
    """Convert every PDF in a directory, continuing after per-file failures.

    Args:
        directory: Root directory to scan for PDFs.
        recursive: When ``True``, scan subdirectories.
        overwrite: When ``True``, replace existing ``.vera`` outputs.
        model: Embedding model name passed to :func:`convert`.
        parser: PDF parser backend passed to :func:`convert`.
        chunk_size: Target chunk size passed to :func:`convert`.
        overlap: Chunk overlap passed to :func:`convert`.
        store_original: Whether to embed originals passed to :func:`convert`.
        ocr_mode: OCR mode passed to :func:`convert`.
        ocr_language: OCR language passed to :func:`convert`.
        ocr_dpi: OCR DPI passed to :func:`convert`.
        progress: Optional ``(current, total, filename)`` callback.
        cancel: Optional cancellation token.

    Returns:
        A report dict with ``converted``, ``skipped``, ``failed``, and related
        fields.

    Raises:
        NotADirectoryError: When ``directory`` is not a directory.
    """
    root = Path(directory).resolve()
    if not root.is_dir():
        raise NotADirectoryError(str(root))

    pdfs: list[Path] = []
    if recursive:
        for current, directories, filenames in os.walk(root, followlinks=False):
            _raise_if_cancelled(cancel)
            directories[:] = sorted(
                name
                for name in directories
                if not (Path(current) / name).is_symlink()
            )
            pdfs.extend(
                Path(current) / name
                for name in sorted(filenames)
                if Path(name).suffix.lower() == ".pdf"
            )
    else:
        _raise_if_cancelled(cancel)
        pdfs = sorted(
            path
            for path in root.iterdir()
            if path.is_file() and path.suffix.lower() == ".pdf"
        )

    outputs: list[str] = []
    skipped_existing: list[str] = []
    skipped_by_user: list[str] = []
    malformed_existing: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    total = len(pdfs)
    if progress and not pdfs:
        progress(0, 0, "")
    for index, pdf in enumerate(pdfs):
        try:
            _raise_if_cancelled(cancel)
            if progress:
                # completed = files finished so far; input = file about to convert
                progress(index, total, str(pdf))
            output = pdf.with_suffix(".vera")
            if output.exists() and not overwrite:
                validation = _validate_output(output)
                if validation["ok"]:
                    skipped_existing.append(str(output))
                else:
                    malformed_existing.append(
                        {
                            "input": str(pdf),
                            "output": str(output),
                            "issues": validation["issues"],
                        }
                    )
                continue
            outputs.append(
                convert(
                    str(pdf),
                    str(output),
                    model=model,
                    parser=parser,
                    chunk_size=chunk_size,
                    overlap=overlap,
                    store_original=store_original,
                    ocr_mode=ocr_mode,
                    ocr_language=ocr_language,
                    ocr_dpi=ocr_dpi,
                    cancel=cancel,
                )
            )
        except Exception as exc:
            if cancel is not None and getattr(cancel, "cancelled", False):
                raise
            if _consume_user_skip(cancel, exc):
                skipped_by_user.append(str(pdf))
                continue
            errors.append({"input": str(pdf), "error": str(exc)})

    if progress and pdfs:
        progress(total, total, str(pdfs[-1]))

    return {
        "directory": str(root),
        "recursive": recursive,
        "overwrite": overwrite,
        "discovered": len(pdfs),
        "converted": len(outputs),
        "skipped": len(skipped_existing),
        "user_skipped": len(skipped_by_user),
        "malformed": len(malformed_existing),
        "failed": len(errors),
        "outputs": outputs,
        "skipped_existing": skipped_existing,
        "skipped_by_user": skipped_by_user,
        "malformed_existing": malformed_existing,
        "errors": errors,
    }
