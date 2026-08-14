"""Attachment storage and streaming I/O for VeraDocument."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable, Iterable, Mapping
from contextlib import AbstractContextManager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ._errors import DuplicateRecordError, RecordNotFoundError
from ._util import _ATTACHMENT_WRITE_CHUNK, _utc_now
from .models import AttachmentRecord, metadata_from_json, metadata_to_json, thaw_json


class _DocumentAttachmentsMixin:
    _conn: sqlite3.Connection

    if TYPE_CHECKING:

        def _ensure_open(self) -> None: ...
        def _ensure_writable(self) -> None: ...
        def _write_scope(self) -> AbstractContextManager[None]: ...

    def put_attachments(
        self,
        attachments: Iterable[AttachmentRecord],
        *,
        upsert: bool = False,
    ) -> None:
        """Store opaque binary attachments.

        Args:
            attachments: Attachment payloads to insert.
            upsert: When ``True``, replace existing attachments with the same ID.

        Raises:
            ReadOnlyError: When the database is opened read-only.
            DuplicateRecordError: When an ID exists and ``upsert`` is false.
        """
        self._ensure_writable()
        items = tuple(attachments)
        if len({item.id for item in items}) != len(items):
            raise ValueError("attachment IDs must be unique within a batch")
        now = _utc_now()
        with self._write_scope():
            for item in items:
                existing = self._conn.execute(
                    "SELECT 1 FROM attachments WHERE attachment_id = ?",
                    (item.id,),
                ).fetchone()
                if existing is not None and not upsert:
                    raise DuplicateRecordError(item.id)
                self._conn.execute(
                    """
                    INSERT INTO attachments(
                        attachment_id, mime_type, filename, data, hash,
                        metadata_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(attachment_id) DO UPDATE SET
                        mime_type = excluded.mime_type,
                        filename = excluded.filename,
                        data = excluded.data,
                        hash = excluded.hash,
                        metadata_json = excluded.metadata_json
                    """,
                    (
                        item.id,
                        item.media_type,
                        item.filename,
                        item.data,
                        item.checksum,
                        metadata_to_json(item.metadata),
                        now,
                    ),
                )

    def get_attachment(self, attachment_id: str) -> AttachmentRecord:
        """Return a stored attachment by ID.

        Args:
            attachment_id: Attachment identifier.

        Returns:
            The matching :class:`~vera_doc.models.AttachmentRecord`.

        Raises:
            RecordNotFoundError: When no attachment exists with that ID.
        """
        self._ensure_open()
        row = self._conn.execute(
            """
            SELECT attachment_id, mime_type, filename, data, hash, metadata_json
            FROM attachments WHERE attachment_id = ?
            """,
            (attachment_id,),
        ).fetchone()
        if row is None:
            raise RecordNotFoundError(attachment_id)
        return self._row_to_attachment(row)

    def write_attachment(
        self,
        attachment_id: str,
        dest: str | os.PathLike[str],
        *,
        chunk_size: int = _ATTACHMENT_WRITE_CHUNK,
        on_chunk: Callable[[int], None] | None = None,
    ) -> int:
        """Copy attachment bytes to ``dest`` without building an in-memory record.

        Prefers SQLite incremental blob I/O when the interpreter provides
        ``Connection.blobopen`` so a large PDF is not materialized as a Python
        ``bytes`` object. Older Pythons fall back to a single ``SELECT``.

        Args:
            attachment_id: Attachment identifier.
            dest: Destination file path. Parent directories are created.
            chunk_size: Write size in bytes.
            on_chunk: Optional callback invoked with bytes written so far before
                each chunk, including a final call after the last write. Useful
                for cooperative cancellation.

        Returns:
            Number of bytes written.

        Raises:
            RecordNotFoundError: When no attachment exists with that ID.
            ValueError: When ``chunk_size`` is less than 1.
        """
        if chunk_size < 1:
            raise ValueError("chunk_size must be at least 1")
        self._ensure_open()
        row = self._conn.execute(
            "SELECT rowid FROM attachments WHERE attachment_id = ?",
            (attachment_id,),
        ).fetchone()
        if row is None:
            raise RecordNotFoundError(attachment_id)
        target = Path(dest)
        target.parent.mkdir(parents=True, exist_ok=True)
        blobopen = getattr(self._conn, "blobopen", None)
        if blobopen is not None:
            try:
                return self._write_attachment_blob(
                    blobopen,
                    int(row["rowid"]),
                    target,
                    chunk_size,
                    on_chunk,
                )
            except (AttributeError, sqlite3.Error):
                pass
        payload = self._conn.execute(
            "SELECT data FROM attachments WHERE attachment_id = ?",
            (attachment_id,),
        ).fetchone()
        if payload is None:
            raise RecordNotFoundError(attachment_id)
        return self._write_attachment_bytes(payload["data"], target, chunk_size, on_chunk)

    @staticmethod
    def _write_attachment_blob(
        blobopen: Callable[..., Any],
        rowid: int,
        target: Path,
        chunk_size: int,
        on_chunk: Callable[[int], None] | None,
    ) -> int:
        written = 0
        with blobopen("attachments", "data", rowid, readonly=True) as blob:
            with target.open("wb") as handle:
                while True:
                    if on_chunk is not None:
                        on_chunk(written)
                    chunk = blob.read(chunk_size)
                    if not chunk:
                        break
                    handle.write(chunk)
                    written += len(chunk)
        if on_chunk is not None:
            on_chunk(written)
        return written

    @staticmethod
    def _write_attachment_bytes(
        payload: Any,
        target: Path,
        chunk_size: int,
        on_chunk: Callable[[int], None] | None,
    ) -> int:
        view = payload if isinstance(payload, memoryview) else memoryview(payload)
        written = 0
        with target.open("wb") as handle:
            while written < len(view):
                if on_chunk is not None:
                    on_chunk(written)
                chunk = view[written : written + chunk_size]
                handle.write(chunk)
                written += len(chunk)
        if on_chunk is not None:
            on_chunk(written)
        return written

    def attachment_metadata(
        self,
        ids: Iterable[str] | None = None,
        *,
        where: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Return attachment descriptors without reading binary payloads.

        Args:
            ids: Specific attachment IDs. When omitted, inspect all attachments.
            where: Exact equality filter on top-level attachment metadata keys.

        Returns:
            Matching descriptors in storage order, or requested ID order when
            ``ids`` is provided. Each descriptor includes ``size`` (payload
            length in bytes) and omits ``data``.
        """
        self._ensure_open()
        requested = tuple(ids) if ids is not None else None
        if requested is not None and not requested:
            return []
        sql = """
            SELECT attachment_id, mime_type, filename, hash, length(data) AS size,
                   metadata_json
            FROM attachments
        """
        params: list[Any] = []
        if requested is not None:
            placeholders = ",".join("?" for _ in requested)
            sql += f" WHERE attachment_id IN ({placeholders})"
            params.extend(requested)
        sql += " ORDER BY attachment_id"
        items = [
            {
                "id": str(row["attachment_id"]),
                "media_type": str(row["mime_type"]),
                "filename": row["filename"],
                "checksum": row["hash"],
                "size": int(row["size"]),
                "metadata": metadata_from_json(row["metadata_json"]),
            }
            for row in self._conn.execute(sql, params)
        ]
        if where:
            items = [
                item
                for item in items
                if all(
                    thaw_json(item["metadata"]).get(key) == expected
                    for key, expected in where.items()
                )
            ]
        if requested is not None:
            by_id = {str(item["id"]): item for item in items}
            items = [by_id[item] for item in requested if item in by_id]
        return items

    def attachments(
        self,
        *,
        where: Mapping[str, Any] | None = None,
    ) -> list[AttachmentRecord]:
        """Return stored attachments, optionally filtered by metadata equality.

        Args:
            where: Exact equality filter on top-level attachment metadata keys.

        Returns:
            Matching attachments in storage order.
        """
        self._ensure_open()
        rows = self._conn.execute(
            """
            SELECT attachment_id, mime_type, filename, data, hash, metadata_json
            FROM attachments
            ORDER BY attachment_id
            """
        ).fetchall()
        items = [self._row_to_attachment(row) for row in rows]
        if not where:
            return items
        return [
            item
            for item in items
            if all(thaw_json(item.metadata).get(key) == expected for key, expected in where.items())
        ]

    @staticmethod
    def _row_to_attachment(row: sqlite3.Row) -> AttachmentRecord:
        return AttachmentRecord(
            id=row["attachment_id"],
            media_type=row["mime_type"],
            filename=row["filename"],
            data=bytes(row["data"]),
            checksum=row["hash"],
            metadata=metadata_from_json(row["metadata_json"]),
        )

    def delete_attachment(self, attachment_id: str) -> None:
        """Delete a stored attachment.

        Args:
            attachment_id: Attachment identifier.

        Raises:
            RecordNotFoundError: When no attachment exists with that ID.
            ValueError: When the attachment is still referenced by a chunk.
            ReadOnlyError: When the database is opened read-only.
        """
        self._ensure_writable()
        with self._write_scope():
            try:
                cursor = self._conn.execute(
                    "DELETE FROM attachments WHERE attachment_id = ?",
                    (attachment_id,),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"attachment {attachment_id!r} is referenced by a chunk") from exc
            if cursor.rowcount == 0:
                raise RecordNotFoundError(attachment_id)
