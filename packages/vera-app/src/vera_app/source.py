"""Export and source-cache sidecar handlers for the PDF viewer."""

from __future__ import annotations

import hashlib
import re
import tempfile
import threading
from pathlib import Path
from typing import Any

from vera_app.cancellation import CancellationToken
from vera_app.documents import open_document
from vera_app.types import Request
from vera_doc import VeraDocument
from vera_ingest.viewer import export_source_document, get_source_document

_SOURCE_COPY_CHUNK = 8 * 1024 * 1024


def export(request: Request) -> dict[str, Any]:
    doc = open_document(str(request["path"]))
    try:
        output = export_source_document(
            doc,
            str(request["output"]) if request.get("output") else None,
        )
        source_doc = get_source_document(doc)
        return {
            "output": output,
            "filename": source_doc.filename,
            "mime_type": source_doc.media_type,
            "hash": source_doc.checksum,
        }
    finally:
        doc.close()


def source_cache_dir(request: Request) -> Path:
    """Return the directory used to materialize embedded source documents.

    Electron passes a stable userData cache dir so the main process can serve
    files over a privileged ``vera-source:`` protocol without shipping PDF
    bytes through the JSON-Lines IPC channel (which freezes the UI on large
    documents). Tests and other callers fall back to the system temp dir.
    """
    configured = request.get("cache_dir")
    if isinstance(configured, str) and configured.strip():
        return Path(configured)
    return Path(tempfile.gettempdir()) / "vera-source-cache"


def source_cache_path(cache_dir: Path, digest: str, filename: str | None) -> Path:
    suffix = Path(filename or "source.bin").suffix or ".bin"
    safe_digest = re.sub(r"[^A-Za-z0-9._-]", "_", digest)
    return cache_dir / f"{safe_digest}{suffix}"


def source_cache_hit(cache_path: Path, expected_size: int) -> bool:
    return cache_path.is_file() and cache_path.stat().st_size == expected_size


def source_result(
    filename: str | None,
    mime_type: str,
    digest: str,
    size: int,
    cache_path: Path,
) -> dict[str, Any]:
    return {
        "filename": filename,
        "mime_type": mime_type,
        "hash": digest,
        "size": size,
        "cache_path": str(cache_path),
    }


def copy_file_to_cache(
    source_path: Path,
    cache_path: Path,
    expected_size: int,
    cancel: CancellationToken | None = None,
) -> Path:
    """Copy a filesystem file into the source cache, reusing an unchanged copy."""
    if cancel:
        cancel.raise_if_cancelled()
    if source_cache_hit(cache_path, expected_size):
        return cache_path
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = cache_path.with_name(f"{cache_path.name}.{threading.get_ident()}.tmp")
    try:
        with source_path.open("rb") as reader, tmp_path.open("wb") as writer:
            copied = 0
            while True:
                if cancel:
                    cancel.raise_if_cancelled()
                chunk = reader.read(_SOURCE_COPY_CHUNK)
                if not chunk:
                    break
                writer.write(chunk)
                copied += len(chunk)
        if copied != expected_size:
            raise ValueError(f"Copied source size mismatch: {source_path}")
        if cancel:
            cancel.raise_if_cancelled()
        tmp_path.replace(cache_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
    return cache_path


def sibling_pdf(path: Path) -> Path | None:
    sibling = path.with_suffix(".pdf")
    if sibling.is_file() and sibling.resolve() != path.resolve():
        return sibling
    return None


def source_from_pdf(
    path: Path,
    cache_dir: Path,
    cancel: CancellationToken | None = None,
) -> dict[str, Any]:
    """Copy a filesystem PDF into the source cache without hashing its bytes."""
    if cancel:
        cancel.raise_if_cancelled()
    if not path.is_file():
        raise FileNotFoundError(f"PDF not found: {path}")
    with path.open("rb") as handle:
        header = handle.read(5)
    if not header.startswith(b"%PDF"):
        raise ValueError(f"Not a PDF file: {path}")
    stat = path.stat()
    digest = hashlib.sha256(
        f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}".encode()
    ).hexdigest()
    cache_path = source_cache_path(cache_dir, digest, path.name)
    copied = copy_file_to_cache(path, cache_path, stat.st_size, cancel)
    return source_result(path.name, "application/pdf", digest, stat.st_size, copied)


def extract_attachment_to_cache(
    doc: VeraDocument,
    attachment_id: str,
    cache_path: Path,
    expected_size: int,
    cancel: CancellationToken | None = None,
) -> Path:
    if cancel:
        cancel.raise_if_cancelled()
    if source_cache_hit(cache_path, expected_size):
        return cache_path
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = cache_path.with_name(f"{cache_path.name}.{threading.get_ident()}.tmp")

    def on_chunk(_written: int) -> None:
        if cancel:
            cancel.raise_if_cancelled()

    try:
        written = doc.write_attachment(attachment_id, tmp_path, on_chunk=on_chunk)
        if written != expected_size:
            raise ValueError("Extracted source size mismatch")
        if cancel:
            cancel.raise_if_cancelled()
        tmp_path.replace(cache_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
    return cache_path


def source(
    request: Request,
    cancel: CancellationToken | None = None,
) -> dict[str, Any]:
    """Materialize a source PDF for the document viewer.

    Large manuals used to exceed the renderer watchdog because this path loaded
    the embedded original into Python, re-hashed it, and only then checked the
    on-disk cache. Cache hits and sibling PDFs now skip that work.
    """
    if cancel:
        cancel.raise_if_cancelled()
    path = Path(str(request["path"]))
    cache_dir = source_cache_dir(request)
    if path.suffix.lower() == ".pdf":
        return source_from_pdf(path, cache_dir, cancel)
    sibling = sibling_pdf(path)
    doc = open_document(str(path))
    try:
        attachment_id = doc.metadata.get("source_attachment_id")
        if attachment_id:
            infos = doc.attachment_metadata([str(attachment_id)])
            if not infos:
                raise ValueError("Original source document is not stored in this archive")
            info = infos[0]
            filename = str(info.get("filename") or "source.pdf")
            mime_type = str(info.get("media_type") or "application/octet-stream")
            digest = str(info.get("checksum") or "")
            size = int(info["size"])
            cache_path = source_cache_path(cache_dir, digest, filename)
            if source_cache_hit(cache_path, size):
                return source_result(filename, mime_type, digest, size, cache_path)
            if sibling is not None and sibling.stat().st_size == size:
                copied = copy_file_to_cache(sibling, cache_path, size, cancel)
                return source_result(filename, mime_type, digest, size, copied)
            extracted = extract_attachment_to_cache(
                doc,
                str(attachment_id),
                cache_path,
                size,
                cancel,
            )
            return source_result(filename, mime_type, digest, size, extracted)
        if sibling is not None:
            return source_from_pdf(sibling, cache_dir, cancel)
        raise ValueError("Original source document is not stored in this archive")
    finally:
        doc.close()
