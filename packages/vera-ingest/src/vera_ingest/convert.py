from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from math import isfinite
from pathlib import Path
from typing import Any

from vera_doc import (
    AttachmentRecord,
    AttachmentRef,
    ChunkRecord,
    EmbeddingFunction,
    VeraDocument,
    get_embedder,
)
from vera_doc.models import (
    METADATA_DOCUMENT_ID,
    METADATA_HEADING_PATH,
    METADATA_PAGE_END,
    METADATA_PAGE_START,
    METADATA_SOURCE_FILENAME,
)
from vera_doc.validation import validate_document

from .cancellation import clear_user_skip, is_user_skip_error, raise_if_cancelled
from .formats import (
    installed_source_formats,
    pipeline_source_formats,
    resolve_ingest_parser,
    source_mime_type,
    source_suffix,
)
from .pipeline import (
    get_ingest_pipeline,
    invoke_ingest_pipeline,
    parse_ingest_pipeline_spec,
    prepare_pipeline_options,
)
from .timing import timed_step
from .types import IngestBlock, IngestRequest, IngestResult


class ReservedMetadataKeyError(ValueError):
    """Caller ``metadata`` collided with a reserved convert or format key."""


_FORMAT_HEADER_KEYS = frozenset(
    {
        "format_name",
        "format_version",
        "created_at",
        "created_by",
        "creator_library",
        "default_embedding_model",
        "default_embedding_dimension",
        "archive_metadata",
        "default_embedding_normalization",
    }
)
_CONVERT_OWNED_ARCHIVE_KEYS = frozenset(
    {
        "source_file_hash",
        "source_file_name",
        "source_mime_type",
        "chunking_strategy",
        "parser_name",
        "parser_version",
        "ocr",
        "page_count",
        "viewer_pages_attachment_id",
        "viewer_blocks_attachment_id",
        "source_attachment_id",
    }
)
_RESERVED_CALLER_METADATA_KEYS = frozenset(
    {
        *_FORMAT_HEADER_KEYS,
        METADATA_PAGE_START,
        METADATA_PAGE_END,
        METADATA_HEADING_PATH,
        METADATA_SOURCE_FILENAME,
        METADATA_DOCUMENT_ID,
        "token_count",
        "regions",
        *_CONVERT_OWNED_ARCHIVE_KEYS,
    }
)


def _is_reserved_metadata_key(key: str) -> bool:
    return (
        key in _RESERVED_CALLER_METADATA_KEYS
        or key.startswith("_vera_")
        or key.startswith("default_embedding_")
    )


def _assert_scalar_metadata_value(key: str, value: Any) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float) and isfinite(value):
        return
    raise ValueError(
        f"metadata {key!r} must be a JSON scalar (string, int, bool, or finite float), "
        f"not {type(value).__name__}"
    )


def _validated_caller_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return caller tags after rejecting reserved keys and nested values."""
    if not metadata:
        return {}
    reserved = []
    validated: dict[str, Any] = {}
    for key, value in metadata.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("metadata keys must be non-empty strings")
        if _is_reserved_metadata_key(key):
            reserved.append(key)
            continue
        _assert_scalar_metadata_value(key, value)
        validated[key] = value
    if reserved:
        names = ", ".join(sorted(reserved))
        raise ReservedMetadataKeyError(f"Reserved metadata key(s): {names}")
    return validated


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


def _stored_source_file_hash(path: Path) -> str | None:
    """Return the archive's stored source SHA-256, or None if missing/unreadable."""
    try:
        with VeraDocument.open(path) as document:
            stored = document.inspect().get("source_file_hash")
    except Exception:
        return None
    if not isinstance(stored, str):
        return None
    digest = stored.strip()
    return digest or None


@dataclass(frozen=True)
class _ConvertSettings:
    """Internal convert/batch_convert settings; not part of the public API."""

    model: str = "hashing"
    embedding_function: EmbeddingFunction | None = None
    parser: str | None = None
    chunk_size: int | None = None
    overlap: int | None = None
    store_original: bool = True
    ocr_mode: str | None = None
    ocr_language: str | None = None
    ocr_dpi: int | None = None
    ocr_download: bool | None = None
    pipeline_options: dict[str, Any] | None = None
    embedder_options: dict[str, Any] | None = None
    cancel: Any | None = None
    metadata: dict[str, Any] | None = None

    def resolve_embedder(self) -> EmbeddingFunction:
        if self.embedding_function is not None:
            return self.embedding_function
        return get_embedder(self.model, embedder_options=self.embedder_options)

    def resolve_pipeline_options(self) -> dict[str, Any]:
        legacy: dict[str, Any] = {}
        for key in (
            "chunk_size",
            "overlap",
            "ocr_mode",
            "ocr_language",
            "ocr_dpi",
            "ocr_download",
        ):
            value = getattr(self, key)
            if value is not None:
                legacy[key] = value
        return prepare_pipeline_options(
            spec=self.parser or "pymupdf",
            pipeline_options=self.pipeline_options,
            legacy_options=legacy,
        )

    def as_convert_kwargs(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "embedding_function": self.embedding_function,
            "parser": self.parser,
            "chunk_size": self.chunk_size,
            "overlap": self.overlap,
            "store_original": self.store_original,
            "ocr_mode": self.ocr_mode,
            "ocr_language": self.ocr_language,
            "ocr_dpi": self.ocr_dpi,
            "ocr_download": self.ocr_download,
            "pipeline_options": self.pipeline_options,
            "embedder_options": self.embedder_options,
            "cancel": self.cancel,
            "metadata": self.metadata,
        }


def _consume_user_skip(cancel: Any | None, exc: BaseException) -> bool:
    """Clear a one-shot skip request if `exc` is a real skip/interrupt."""
    if cancel is None:
        return False
    if getattr(cancel, "cancelled", False):
        return False
    if not is_user_skip_error(exc):
        return False
    clear_user_skip(cancel)
    return True


def _validate_ingest_result(result: IngestResult) -> None:
    block_ids = [block.block_id for block in result.blocks]
    chunk_ids = [chunk.chunk_id for chunk in result.chunks]
    if any(not block_id.strip() for block_id in block_ids):
        raise ValueError("Ingest pipeline produced an empty block ID")
    if len(block_ids) != len(set(block_ids)):
        raise ValueError("Ingest pipeline produced duplicate block IDs")
    if any(not chunk_id.strip() for chunk_id in chunk_ids):
        raise ValueError("Ingest pipeline produced an empty chunk ID")
    if len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError("Ingest pipeline produced duplicate chunk IDs")
    known_blocks = set(block_ids)
    for chunk in result.chunks:
        unknown = set(chunk.block_ids) - known_blocks
        if unknown:
            names = ", ".join(sorted(unknown))
            raise ValueError(
                f"Ingest chunk {chunk.chunk_id!r} references unknown block IDs: {names}"
            )
        if not chunk.text.strip():
            raise ValueError(f"Ingest chunk {chunk.chunk_id!r} has no readable text")


def _regions_for_block(
    block: IngestBlock,
    block_id: str,
    page_dimensions: dict[int, tuple[float | None, float | None]],
) -> list[dict[str, Any]]:
    """Copy contributing locators, including non-bbox ``text_span`` regions."""
    if block.block_type == "image":
        return []
    explicit_regions = list(block.regions)
    if not explicit_regions and block.bbox:
        explicit_regions = [
            {
                "kind": "page_bbox",
                "page_number": block.page_number,
                "bbox": block.bbox,
            }
        ]
    regions: list[dict[str, Any]] = []
    for explicit in explicit_regions:
        region = {**explicit, "block_id": block_id}
        bbox = explicit.get("bbox")
        if bbox is not None:
            page_number = int(explicit.get("page_number", block.page_number))
            width, height = page_dimensions.get(page_number, (None, None))
            region["kind"] = explicit.get("kind") or "page_bbox"
            region["page_number"] = page_number
            region["bbox"] = list(bbox)
            region["page_width"] = explicit.get("page_width", width)
            region["page_height"] = explicit.get("page_height", height)
        else:
            region.setdefault("kind", "text_span")
        regions.append(region)
    return regions


def convert(
    input_path: str,
    output_path: str,
    *,
    model: str = "hashing",
    embedding_function: EmbeddingFunction | None = None,
    parser: str | None = None,
    chunk_size: int | None = None,
    overlap: int | None = None,
    store_original: bool = True,
    ocr_mode: str | None = None,
    ocr_language: str | None = None,
    ocr_dpi: int | None = None,
    ocr_download: bool | None = None,
    pipeline_options: dict[str, Any] | None = None,
    embedder_options: dict[str, Any] | None = None,
    cancel: Any | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> str:
    """Convert a source document into a validated ``.vera`` archive.

    Parses the file, chunks extracted text, embeds chunks, and writes the
    result through :class:`~vera_doc.document.VeraDocument`. The archive is
    validated before the temporary file is published atomically.

    New callers should pass ``parser``, ``pipeline_options``, and embedder
    settings (``model`` / ``embedding_function`` / ``embedder_options``).
    ``chunk_size``, ``overlap``, ``ocr_mode``, ``ocr_language``, ``ocr_dpi``,
    and ``ocr_download`` remain compatibility aliases for CLI and sidecar
    callers; they are forwarded only when explicitly provided *and* the
    selected pipeline advertises them (Tesseract OCR aliases do not leak
    to Docling). Omitted aliases mean "use the pipeline's own default"
    (for example a plugin ``chunk_size`` of 2000 is not overwritten by 500).
    The CLI still passes its argparse defaults when invoked from the command
    line.

    Args:
        input_path: Source document path (PDF, Markdown, or another format
            advertised by an installed ingest pipeline).
        output_path: Destination ``.vera`` path.
        model: Embedding model spec (default ``"hashing"``). Ignored when
            ``embedding_function`` is provided. Accepts ``provider:model-id``
            or built-in legacy aliases.
        embedding_function: Optional custom embedder satisfying
            :class:`~vera_doc.EmbeddingFunction`. When omitted, ``model`` is
            resolved via :func:`~vera_doc.get_embedder` before parsing begins.
        parser: Ingest pipeline spec in ``provider[:variant]`` form. ``None``
            (the default) selects an installed pipeline from the file
            extension. An explicit spec must advertise that extension.
        chunk_size: Compatibility alias forwarded only when explicitly
            provided and the selected pipeline advertises a ``chunk_size``
            field. ``None`` (the default) means the pipeline default.
        overlap: Compatibility alias forwarded only when explicitly provided
            and advertised by the selected pipeline (PyMuPDF, Markdown).
            Ignored by Docling. ``None`` means the pipeline default.
        store_original: When ``True``, embed the original file as an attachment.
        ocr_mode: Compatibility OCR mode alias when explicitly provided and
            advertised by the pipeline. ``None`` means the pipeline default.
        ocr_language: Tesseract OCR language alias (PyMuPDF). Forwarded only
            when explicitly provided and the selected pipeline's
            ``ocr_engine`` is ``"tesseract"``. ``None`` means the pipeline
            default.
        ocr_dpi: Compatibility OCR DPI alias when explicitly provided and
            advertised (PyMuPDF). ``None`` means the pipeline default.
        ocr_download: Compatibility alias (PyMuPDF only) allowing on-demand,
            checksum-verified download of missing Tesseract language data.
            ``None`` means the pipeline default.
        pipeline_options: Explicit provider-owned options. These override
            compatibility aliases for the same keys.
        embedder_options: Explicit provider-owned embedding options forwarded
            to :func:`~vera_doc.get_embedder` when ``embedding_function`` is omitted.
        cancel: Optional cancellation token with ``raise_if_cancelled()``.
        metadata: Extra keys stamped onto archive metadata and every chunk.
            Reserved ingest, citation, and format keys are rejected.

    Returns:
        The ``output_path`` string.

    Raises:
        FileNotFoundError: When ``input_path`` does not exist.
        ValueError: When no searchable text is extracted, or ``parser`` does
            not support the source file type.
        ReservedMetadataKeyError: When ``metadata`` uses a reserved key.
        UnknownIngestPipelineError: When ``parser`` cannot be resolved.
        UnknownEmbeddingModelError: When ``model`` cannot be resolved.
    """
    source = Path(input_path)
    target = Path(output_path)
    if not source.exists():
        raise FileNotFoundError(input_path)

    settings = _ConvertSettings(
        model=model,
        embedding_function=embedding_function,
        parser=parser,
        chunk_size=chunk_size,
        overlap=overlap,
        store_original=store_original,
        ocr_mode=ocr_mode,
        ocr_language=ocr_language,
        ocr_dpi=ocr_dpi,
        ocr_download=ocr_download,
        pipeline_options=pipeline_options,
        embedder_options=embedder_options,
        cancel=cancel,
        metadata=_validated_caller_metadata(metadata) or None,
    )
    resolved_parser = resolve_ingest_parser(source, settings.parser)
    settings = replace(settings, parser=resolved_parser)
    with timed_step("resolve_pipeline", parser=settings.parser):
        _, pipeline_variant = parse_ingest_pipeline_spec(settings.parser)
        pipeline = get_ingest_pipeline(settings.parser)
    with timed_step("resolve_embedder", model=settings.model):
        embedder = settings.resolve_embedder()
    resolved_options = settings.resolve_pipeline_options()

    raise_if_cancelled(settings.cancel)
    source_data = source.read_bytes()
    source_hash = _sha256_bytes(source_data)
    mime_type = source_mime_type(source)
    with timed_step("ingest", parser=settings.parser, file=source.name):
        ingest_result = invoke_ingest_pipeline(
            pipeline,
            str(source),
            IngestRequest(
                variant=pipeline_variant,
                cancel=settings.cancel,
                pipeline_options=resolved_options,
            ),
        )
    raise_if_cancelled(settings.cancel)
    _validate_ingest_result(ingest_result)
    pages = ingest_result.pages
    block_records: list[tuple[str, IngestBlock]] = [
        (block.block_id, block) for block in ingest_result.blocks
    ]
    chunks = ingest_result.chunks
    if not chunks:
        if source_suffix(source) == "pdf":
            raise ValueError(
                "No searchable text or chunks were extracted; "
                "the PDF may be scanned and requires OCR."
            )
        raise ValueError("No searchable text or chunks were extracted from this file.")
    raise_if_cancelled(settings.cancel)
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
        page_dimensions = {page.page_number: (page.width, page.height) for page in pages}
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
        if settings.store_original:
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

        caller_metadata = settings.metadata or {}
        archive_metadata = {
            "title": source.stem,
            "source_file_name": source.name,
            "source_file_hash": source_hash,
            "source_mime_type": mime_type,
            "chunking_strategy": ingest_result.chunking_strategy,
            "parser_name": ingest_result.parser_name,
            "parser_version": ingest_result.parser_version,
            "ocr": ingest_result.diagnostics,
            "page_count": len(pages),
            "viewer_pages_attachment_id": "viewer_pages",
            "viewer_blocks_attachment_id": "viewer_blocks",
            "source_attachment_id": source_attachment_id,
            **caller_metadata,
        }
        contextualized_indices = [
            index for index, chunk in enumerate(chunks) if chunk.embedding_text is not None
        ]
        contextualized_vectors: dict[int, Any] = {}
        with timed_step("embed", model=settings.model, chunks=len(contextualized_indices)):
            if contextualized_indices:
                vectors = embedder.embed(
                    [chunks[index].embedding_text or "" for index in contextualized_indices]
                )
                contextualized_vectors = dict(zip(contextualized_indices, vectors))
                raise_if_cancelled(settings.cancel)
        records: list[ChunkRecord] = []
        for index, chunk in enumerate(chunks):
            regions = []
            references: list[AttachmentRef] = []
            for block_id in chunk.block_ids:
                block = block_lookup.get(block_id)
                if block is None:
                    continue
                regions.extend(_regions_for_block(block, block_id, page_dimensions))
                image_attachment_id = image_attachment_by_block.get(block_id)
                if image_attachment_id:
                    references.append(AttachmentRef(image_attachment_id, role="figure"))
            if source_attachment_id:
                references.append(AttachmentRef(source_attachment_id, role="source"))
            records.append(
                ChunkRecord(
                    id=chunk.chunk_id,
                    text=chunk.text,
                    metadata={
                        **chunk.metadata,
                        "document_id": "document_0001",
                        "source_filename": source.name,
                        "page_start": chunk.page_start,
                        "page_end": chunk.page_end,
                        "heading_path": chunk.heading_path,
                        "token_count": chunk.token_count,
                        "regions": regions,
                        **caller_metadata,
                    },
                    attachments=tuple(references),
                    vector=contextualized_vectors.get(index),
                )
            )

        with timed_step("write_archive", file=target.name, chunks=len(records)):
            document = VeraDocument.create(
                temporary,
                embedding_function=embedder,
                metadata=archive_metadata,
            )
            with document.transaction():
                document.put_attachments(attachments)
                document.add(records)
            document.close()
            document = None
            raise_if_cancelled(settings.cancel)

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


def _resolve_batch_sources(
    directory: str | None,
    *,
    paths: Sequence[str] | None,
    recursive: bool,
    parser: str | None,
    cancel: Any | None,
) -> tuple[Path, list[Path]]:
    """Return ``(report_root, sources)`` for directory discovery or an explicit list."""
    suffixes = (
        set(pipeline_source_formats(parser)) if parser else set(installed_source_formats())
    )
    if not suffixes:
        raise ValueError("No installed ingest pipeline advertises source formats to convert.")

    def is_source(path: Path) -> bool:
        return path.is_file() and source_suffix(path) in suffixes

    if paths is not None:
        if not paths:
            raise ValueError("paths must not be empty when provided")
        sources: list[Path] = []
        for raw in paths:
            raise_if_cancelled(cancel)
            path = Path(raw).expanduser().resolve()
            if not path.is_file():
                raise FileNotFoundError(f"Source file not found: {path}")
            if source_suffix(path) not in suffixes:
                supported = ", ".join(f".{item}" for item in sorted(suffixes))
                raise ValueError(f"Not a supported source file ({supported}): {path}")
            sources.append(path)
        try:
            root = Path(os.path.commonpath([str(path.parent) for path in sources]))
        except ValueError:
            # Different drives on Windows — fall back to the first parent.
            root = sources[0].parent
        return root, sources

    if directory is None or not str(directory).strip():
        raise ValueError("directory is required when paths is not provided")
    root = Path(directory).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(str(root))

    sources = []
    if recursive:
        for current, directories, filenames in os.walk(root, followlinks=False):
            raise_if_cancelled(cancel)
            directories[:] = sorted(
                name for name in directories if not (Path(current) / name).is_symlink()
            )
            sources.extend(
                Path(current) / name for name in sorted(filenames) if is_source(Path(current) / name)
            )
    else:
        raise_if_cancelled(cancel)
        sources = sorted(path for path in root.iterdir() if is_source(path))
    return root, sources


def batch_convert(
    directory: str | None = None,
    *,
    paths: Sequence[str] | None = None,
    recursive: bool = False,
    overwrite: bool = False,
    model: str = "hashing",
    embedding_function: EmbeddingFunction | None = None,
    parser: str | None = None,
    chunk_size: int | None = None,
    overlap: int | None = None,
    store_original: bool = True,
    ocr_mode: str | None = None,
    ocr_language: str | None = None,
    ocr_dpi: int | None = None,
    ocr_download: bool | None = None,
    pipeline_options: dict[str, Any] | None = None,
    embedder_options: dict[str, Any] | None = None,
    progress: Callable[[int, int, str], None] | None = None,
    cancel: Any | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert source files from a directory scan or an explicit path list.

    Args:
        directory: Root directory to scan when ``paths`` is omitted. Discovery
            uses the selected pipeline's ``source_formats``, or every installed
            pipeline when ``parser`` is omitted.
        paths: Explicit source file paths to convert. When set, directory
            discovery is skipped and ``recursive`` is ignored.
        recursive: When ``True``, scan subdirectories (directory mode only).
        overwrite: When ``True``, replace existing ``.vera`` outputs. When
            ``False``, skip a sibling archive only when it validates and its
            stored ``source_file_hash`` matches the current source file. Stale or
            hash-less archives are reconverted.
        model: Embedding model spec passed to :func:`convert`.
        embedding_function: Optional custom embedder passed to :func:`convert`.
        parser: Ingest pipeline spec passed to :func:`convert`. ``None``
            (the default) selects a pipeline per file from its extension.
        chunk_size: Compatibility alias passed to :func:`convert`. ``None``
            means the pipeline default.
        overlap: Compatibility alias passed to :func:`convert`. ``None``
            means the pipeline default.
        store_original: Whether to embed originals passed to :func:`convert`.
        ocr_mode: Compatibility OCR mode alias passed to :func:`convert`.
            ``None`` means the pipeline default.
        ocr_language: Compatibility OCR language alias passed to :func:`convert`.
            ``None`` means the pipeline default.
        ocr_dpi: Compatibility OCR DPI alias passed to :func:`convert`.
            ``None`` means the pipeline default.
        ocr_download: Compatibility OCR download alias passed to :func:`convert`.
            ``None`` means the pipeline default.
        pipeline_options: Explicit provider-owned options passed to :func:`convert`.
        embedder_options: Explicit provider-owned embedding options passed to
            :func:`convert`.
        progress: Optional ``(current, total, filename)`` callback.
        cancel: Optional cancellation token.
        metadata: Extra keys stamped onto every archive and chunk in this run.

    Returns:
        A report dict with ``converted``, ``skipped``, ``failed``, and related
        fields. ``directory`` is the scan root, or the common parent of
        ``paths``.

    Raises:
        NotADirectoryError: When ``directory`` is not a directory.
        FileNotFoundError: When a path in ``paths`` is missing.
        ValueError: When neither ``directory`` nor ``paths`` is usable.
        ReservedMetadataKeyError: When ``metadata`` uses a reserved key.
        UnknownEmbeddingModelError: When ``model`` cannot be resolved.
    """
    settings = _ConvertSettings(
        model=model,
        embedding_function=embedding_function,
        parser=parser,
        chunk_size=chunk_size,
        overlap=overlap,
        store_original=store_original,
        ocr_mode=ocr_mode,
        ocr_language=ocr_language,
        ocr_dpi=ocr_dpi,
        ocr_download=ocr_download,
        pipeline_options=pipeline_options,
        embedder_options=embedder_options,
        cancel=cancel,
        metadata=_validated_caller_metadata(metadata) or None,
    )
    # Resolve an explicit parser up front so a bad provider fails before discovery.
    if settings.parser:
        with timed_step("resolve_pipeline", parser=settings.parser):
            get_ingest_pipeline(settings.parser)
    with timed_step("resolve_embedder", model=settings.model):
        embedder = settings.resolve_embedder()
    file_settings = replace(settings, embedding_function=embedder)

    root, sources = _resolve_batch_sources(
        directory,
        paths=paths,
        recursive=recursive,
        parser=settings.parser,
        cancel=settings.cancel,
    )

    outputs: list[str] = []
    skipped_existing: list[str] = []
    skipped_by_user: list[str] = []
    malformed_existing: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    total = len(sources)
    if progress and not sources:
        progress(0, 0, "")
    for index, source_file in enumerate(sources):
        try:
            raise_if_cancelled(settings.cancel)
            if progress:
                # completed = files finished so far; input = file about to convert
                progress(index, total, str(source_file))
            output = source_file.with_suffix(".vera")
            if output.exists() and not overwrite:
                validation = _validate_output(output)
                if not validation["ok"]:
                    malformed_existing.append(
                        {
                            "input": str(source_file),
                            "output": str(output),
                            "issues": validation["issues"],
                        }
                    )
                    continue
                stored_hash = _stored_source_file_hash(output)
                current_hash = _sha256_bytes(source_file.read_bytes())
                raise_if_cancelled(settings.cancel)
                if stored_hash is not None and stored_hash == current_hash:
                    clear_user_skip(settings.cancel)
                    skipped_existing.append(str(output))
                    continue
            outputs.append(
                convert(
                    str(source_file),
                    str(output),
                    **file_settings.as_convert_kwargs(),
                )
            )
        except Exception as exc:
            if settings.cancel is not None and getattr(settings.cancel, "cancelled", False):
                raise
            if _consume_user_skip(settings.cancel, exc):
                skipped_by_user.append(str(source_file))
                continue
            errors.append({"input": str(source_file), "error": str(exc)})

    if progress and sources:
        progress(total, total, str(sources[-1]))

    return {
        "directory": str(root),
        "recursive": False if paths is not None else recursive,
        "overwrite": overwrite,
        "discovered": len(sources),
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
