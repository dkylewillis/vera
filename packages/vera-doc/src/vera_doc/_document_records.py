"""Chunk CRUD, vector validation, and FTS row maintenance for VeraDocument."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, Any

import numpy as np

from ._errors import DuplicateRecordError, RecordNotFoundError
from ._util import (
    _L2_NORMALIZATION_ATOL,
    _L2_NORMALIZATION_RTOL,
    _SQL_VARIABLE_BATCH,
    _batched,
    _embedding_normalization,
    _utc_now,
)
from .embeddings import EmbeddingFunction, deserialize_vector, serialize_vector
from .models import AttachmentRef, ChunkRecord, metadata_from_json, metadata_to_json, thaw_json


class _DocumentRecordsMixin:
    _conn: sqlite3.Connection
    _embedding_function: EmbeddingFunction | None

    if TYPE_CHECKING:

        def _ensure_open(self) -> None: ...
        def _ensure_writable(self) -> None: ...
        def _write_scope(self) -> AbstractContextManager[None]: ...
        def _metadata_values(self) -> dict[str, str]: ...

    def add(self, records: Iterable[ChunkRecord]) -> None:
        """Insert new chunk records.

        Args:
            records: Records to insert. IDs must not already exist.

        Raises:
            DuplicateRecordError: When a record ID already exists.
            ReadOnlyError: When the database is opened read-only.
            RecordNotFoundError: When an attachment reference is missing.
        """
        self._write_records(records, upsert=False)

    def upsert(self, records: Iterable[ChunkRecord]) -> None:
        """Insert or replace chunk records atomically.

        Args:
            records: Records to insert or update by ID.

        Raises:
            ReadOnlyError: When the database is opened read-only.
            RecordNotFoundError: When an attachment reference is missing.
        """
        self._write_records(records, upsert=True)

    def _write_records(
        self,
        records: Iterable[ChunkRecord],
        *,
        upsert: bool,
    ) -> None:
        self._ensure_writable()
        items = tuple(records)
        if not items:
            return
        if len({record.id for record in items}) != len(items):
            raise ValueError("record IDs must be unique within a batch")
        vectors = self._vectors_for(items)
        now = _utc_now()
        model_values = self._metadata_values()
        model_name = model_values["default_embedding_model"]
        dimension = int(model_values["default_embedding_dimension"])
        with self._write_scope():
            attachment_ids = {
                row["attachment_id"]
                for row in self._conn.execute("SELECT attachment_id FROM attachments")
            }
            for record, vector in zip(items, vectors):
                missing = {
                    ref.attachment_id
                    for ref in record.attachments
                    if ref.attachment_id not in attachment_ids
                }
                if missing:
                    raise RecordNotFoundError(
                        f"unknown attachment IDs: {', '.join(sorted(missing))}"
                    )
                existing = self._conn.execute(
                    "SELECT created_at FROM chunks WHERE chunk_id = ?",
                    (record.id,),
                ).fetchone()
                if existing is not None and not upsert:
                    raise DuplicateRecordError(record.id)
                created_at = existing["created_at"] if existing is not None else now
                self._conn.execute(
                    """
                    INSERT INTO chunks(chunk_id, text, metadata_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(chunk_id) DO UPDATE SET
                        text = excluded.text,
                        metadata_json = excluded.metadata_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        record.id,
                        record.text,
                        metadata_to_json(record.metadata),
                        created_at,
                        now,
                    ),
                )
                self._conn.execute(
                    """
                    INSERT INTO embeddings(
                        chunk_id, model_name, model_dimension, vector, vector_format, created_at
                    ) VALUES (?, ?, ?, ?, 'float32_le', ?)
                    ON CONFLICT(chunk_id) DO UPDATE SET
                        model_name = excluded.model_name,
                        model_dimension = excluded.model_dimension,
                        vector = excluded.vector,
                        vector_format = excluded.vector_format,
                        created_at = excluded.created_at
                    """,
                    (
                        record.id,
                        model_name,
                        dimension,
                        serialize_vector(vector),
                        now,
                    ),
                )
                if existing is not None:
                    self._replace_fts_row(record.id, record.text)
                else:
                    self._insert_fts_row(record.id, record.text)
                self._conn.execute(
                    "DELETE FROM chunk_attachments WHERE chunk_id = ?",
                    (record.id,),
                )
                self._conn.executemany(
                    """
                    INSERT INTO chunk_attachments(chunk_id, attachment_id, role)
                    VALUES (?, ?, ?)
                    """,
                    [(record.id, ref.attachment_id, ref.role or "") for ref in record.attachments],
                )

    def _vectors_for(self, records: Sequence[ChunkRecord]) -> list[np.ndarray]:
        metadata = self._metadata_values()
        expected = int(metadata["default_embedding_dimension"])
        normalization = _embedding_normalization(metadata.get("default_embedding_normalization"))
        generated_indices = [index for index, record in enumerate(records) if record.vector is None]
        generated: dict[int, np.ndarray] = {}
        if generated_indices:
            if self._embedding_function is None:
                raise ValueError("records without vectors require an embedding_function")
            matrix = self._embedding_function.embed(
                [records[index].text for index in generated_indices]
            )
            for index, vector in zip(generated_indices, matrix):
                generated[index] = np.asarray(vector, dtype=np.float32)
        vectors: list[np.ndarray] = []
        for index, record in enumerate(records):
            vector = (
                generated[index]
                if record.vector is None
                else np.asarray(record.vector, dtype=np.float32)
            )
            if vector.ndim != 1 or vector.size != expected:
                raise ValueError(
                    f"record {record.id!r} vector dimension {vector.size} "
                    f"does not match database dimension {expected}"
                )
            if not np.isfinite(vector).all():
                raise ValueError(f"record {record.id!r} vector is not finite")
            norm = float(np.linalg.norm(vector))
            if (
                normalization == "l2"
                and norm != 0.0
                and not np.isclose(
                    norm,
                    1.0,
                    rtol=_L2_NORMALIZATION_RTOL,
                    atol=_L2_NORMALIZATION_ATOL,
                )
            ):
                raise ValueError(
                    f"record {record.id!r} vector is not L2-normalized (norm {norm:.8g})"
                )
            vectors.append(vector)
        return vectors

    def get(
        self,
        ids: Iterable[str] | None = None,
        *,
        where: Mapping[str, Any] | None = None,
        limit: int | None = None,
    ) -> list[ChunkRecord]:
        """Fetch chunk records by ID and/or metadata filter.

        Args:
            ids: Specific chunk IDs to retrieve. When omitted, all matching
                records are returned subject to ``where`` and ``limit``.
            where: Exact equality filter on top-level metadata keys.
            limit: Maximum number of records to return.

        Returns:
            Matching :class:`~vera_doc.models.ChunkRecord` objects in storage order.
        """
        self._ensure_open()
        if limit is not None and limit < 0:
            raise ValueError("limit must be non-negative")
        requested = tuple(ids) if ids is not None else None
        if requested is not None and not requested:
            return []
        sql = """
            SELECT c.chunk_id, c.text, c.metadata_json, e.vector
            FROM chunks c
            JOIN embeddings e ON e.chunk_id = c.chunk_id
        """
        if requested is None:
            rows = self._conn.execute(f"{sql} ORDER BY c.rowid").fetchall()
        else:
            rows = []
            for batch in _batched(requested, _SQL_VARIABLE_BATCH):
                placeholders = ",".join("?" for _ in batch)
                rows.extend(
                    self._conn.execute(
                        f"{sql} WHERE c.chunk_id IN ({placeholders}) ORDER BY c.rowid",
                        batch,
                    ).fetchall()
                )
        refs = self._attachment_refs([str(row["chunk_id"]) for row in rows])
        records = [self._row_to_record(row, refs.get(str(row["chunk_id"]), ())) for row in rows]
        records = [record for record in records if self._metadata_matches(record, where)]
        if requested is not None:
            by_id = {record.id: record for record in records}
            records = [by_id[item] for item in requested if item in by_id]
        return records if limit is None else records[:limit]

    def delete(
        self,
        ids: Iterable[str] | None = None,
        *,
        where: Mapping[str, Any] | None = None,
        delete_all: bool = False,
    ) -> int:
        """Delete chunk records by ID and/or metadata filter.

        Args:
            ids: Specific chunk IDs to delete.
            where: Exact equality filter on top-level metadata keys.
            delete_all: Required to delete every chunk when ``ids`` and
                ``where`` are omitted.

        Returns:
            The number of records deleted.

        Raises:
            ValueError: When neither ``ids`` nor ``where`` is given and
                ``delete_all`` is false.
        """
        self._ensure_writable()
        if ids is None and not where and not delete_all:
            raise ValueError("delete() requires ids, where, or delete_all=True")
        records = self.get(ids, where=where)
        if not records:
            return 0
        with self._write_scope():
            for record in records:
                self._delete_fts_row(record.id)
                self._conn.execute(
                    "DELETE FROM chunks WHERE chunk_id = ?",
                    (record.id,),
                )
        return len(records)

    def _row_to_record(
        self,
        row: sqlite3.Row,
        attachments: tuple[AttachmentRef, ...] = (),
    ) -> ChunkRecord:
        return ChunkRecord(
            id=row["chunk_id"],
            text=row["text"],
            metadata=metadata_from_json(row["metadata_json"]),
            vector=tuple(float(value) for value in deserialize_vector(row["vector"])),
            attachments=attachments,
        )

    def _attachment_refs(self, chunk_ids: Sequence[str]) -> dict[str, tuple[AttachmentRef, ...]]:
        refs: dict[str, list[AttachmentRef]] = {chunk_id: [] for chunk_id in chunk_ids}
        if not chunk_ids:
            return {}
        for batch in _batched(chunk_ids, _SQL_VARIABLE_BATCH):
            placeholders = ",".join("?" for _ in batch)
            for row in self._conn.execute(
                f"""
                SELECT chunk_id, attachment_id, role
                FROM chunk_attachments
                WHERE chunk_id IN ({placeholders})
                ORDER BY chunk_id, attachment_id, role
                """,
                batch,
            ):
                refs[str(row["chunk_id"])].append(
                    AttachmentRef(
                        attachment_id=row["attachment_id"],
                        role=row["role"] or None,
                    )
                )
        return {chunk_id: tuple(values) for chunk_id, values in refs.items()}

    def _chunk_rowid(self, chunk_id: str) -> int | None:
        row = self._conn.execute(
            "SELECT rowid FROM chunks WHERE chunk_id = ?",
            (chunk_id,),
        ).fetchone()
        return int(row["rowid"]) if row is not None else None

    def _insert_fts_row(self, chunk_id: str, text: str) -> None:
        chunk_rowid = self._chunk_rowid(chunk_id)
        if chunk_rowid is None or self._fts_rowid_taken(chunk_rowid, chunk_id):
            # Archives written before FTS rows were aligned to chunks.rowid can
            # have another chunk squatting this rowid. Appending keeps the write
            # working; alignment is an optimization, not a format requirement.
            self._conn.execute(
                "INSERT INTO chunks_fts(chunk_id, text) VALUES (?, ?)",
                (chunk_id, text),
            )
            return
        self._conn.execute(
            "INSERT INTO chunks_fts(rowid, chunk_id, text) VALUES (?, ?, ?)",
            (chunk_rowid, chunk_id, text),
        )

    def _fts_rowid_taken(self, rowid: int, chunk_id: str) -> bool:
        row = self._conn.execute(
            "SELECT chunk_id FROM chunks_fts WHERE rowid = ?",
            (rowid,),
        ).fetchone()
        return row is not None and str(row["chunk_id"]) != chunk_id

    def _replace_fts_row(self, chunk_id: str, text: str) -> None:
        self._delete_fts_row(chunk_id)
        self._insert_fts_row(chunk_id, text)

    def _delete_fts_row(self, chunk_id: str) -> None:
        chunk_rowid = self._chunk_rowid(chunk_id)
        if chunk_rowid is not None:
            existing = self._conn.execute(
                "SELECT chunk_id FROM chunks_fts WHERE rowid = ?",
                (chunk_rowid,),
            ).fetchone()
            if existing is not None and str(existing["chunk_id"]) == chunk_id:
                self._conn.execute(
                    "DELETE FROM chunks_fts WHERE rowid = ?",
                    (chunk_rowid,),
                )
                return
        self._conn.execute(
            "DELETE FROM chunks_fts WHERE chunk_id = ?",
            (chunk_id,),
        )

    @staticmethod
    def _metadata_matches(
        record: ChunkRecord,
        where: Mapping[str, Any] | None,
    ) -> bool:
        if not where:
            return True
        metadata = thaw_json(record.metadata)
        return all(metadata.get(key) == expected for key, expected in where.items())
