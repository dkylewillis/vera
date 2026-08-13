from __future__ import annotations

import os
import sqlite3
import tempfile
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np

from ._schema import FORMAT_VERSION, create_schema
from .embeddings import (
    EmbeddingFunction,
    deserialize_vector,
    get_embedder,
    serialize_vector,
)
from .models import (
    AttachmentRecord,
    AttachmentRef,
    ChunkRecord,
    JsonObject,
    QueryResult,
    metadata_from_json,
    metadata_to_json,
    thaw_json,
)
from .validation import validate_document

OpenMode = Literal["read", "write"]
SearchMode = Literal["semantic", "keyword", "hybrid"]
EmbeddingNormalization = Literal["l2", "none", "unknown"]
_EMBEDDING_NORMALIZATIONS = frozenset({"l2", "none", "unknown"})
_L2_NORMALIZATION_RTOL = 1e-4
_L2_NORMALIZATION_ATOL = 1e-6
_MAX_TOP_K = 10_000
_FTS_RUNTIME_MARKERS = (
    "database is locked",
    "database disk image is malformed",
    "no such table",
    "no such module",
    "unable to open database",
    "disk i/o error",
    "attempt to write a readonly",
    "locking protocol",
)


def _package_version() -> str:
    try:
        return package_version("vera-doc")
    except PackageNotFoundError:
        return "0.3.0"


def is_fts_syntax_error(exc: BaseException) -> bool:
    """Return True when ``exc`` is an FTS query-syntax failure, not a runtime error."""
    if not isinstance(exc, sqlite3.OperationalError):
        return False
    message = str(exc).lower()
    if any(marker in message for marker in _FTS_RUNTIME_MARKERS):
        return False
    return True


def safe_fts_query(raw: str) -> str:
    """Return an OR-joined prefix query, or empty when no safe tokens remain."""
    terms = []
    for token in raw.split():
        cleaned = "".join(
            character for character in token if character.isalnum() or character == "_"
        )
        if cleaned:
            terms.append(f"{cleaned}*")
    return " OR ".join(terms)


def execute_fts(
    conn: sqlite3.Connection,
    sql: str,
    query: str,
    *params: Any,
) -> list[sqlite3.Row]:
    """Run an FTS MATCH query; syntax errors become empty hits, other errors raise."""
    try:
        return conn.execute(sql, (query, *params)).fetchall()
    except sqlite3.OperationalError as exc:
        if not is_fts_syntax_error(exc):
            raise
        return []


class DuplicateRecordError(ValueError):
    """Raised when add() receives an ID that already exists."""


class RecordNotFoundError(KeyError):
    """Raised when a requested chunk or attachment does not exist."""


class ReadOnlyError(PermissionError):
    """Raised when a write is attempted on a read-only database."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize_scores(scores: Mapping[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    values = list(scores.values())
    low, high = min(values), max(values)
    if high == low:
        return {key: 1.0 for key in scores}
    return {key: (value - low) / (high - low) for key, value in scores.items()}


def _embedding_normalization(
    value: str | None,
    *,
    default: str = "unknown",
) -> EmbeddingNormalization:
    normalization = (value or default).strip().lower()
    if normalization not in _EMBEDDING_NORMALIZATIONS:
        choices = ", ".join(sorted(_EMBEDDING_NORMALIZATIONS))
        raise ValueError(f"embedding normalization must be one of: {choices}")
    return cast(EmbeddingNormalization, normalization)


class VeraDocument:
    """An embedded storage and search engine backed by one portable ``.vera`` file.

    Use :meth:`create` to initialize a new archive and :meth:`open` to access
    an existing one. Archives support CRUD on :class:`~vera_doc.models.ChunkRecord`
    objects, optional binary attachments, and semantic, keyword, or hybrid
    search.

    Example:
        ```python
        from vera_doc import ChunkRecord, VeraDocument

        with VeraDocument.create("example.vera") as document:
            document.add([ChunkRecord(id="1", text="Hello world.")])

        with VeraDocument.open("example.vera") as document:
            results = document.search(text="hello", top_k=5)
        ```
    """

    def __init__(
        self,
        path: Path,
        conn: sqlite3.Connection,
        *,
        mode: OpenMode,
        embedding_function: EmbeddingFunction | None,
    ) -> None:
        self.path = path
        self._conn = conn
        self._conn.row_factory = sqlite3.Row
        self._mode = mode
        self._embedding_function = embedding_function
        self._transaction_active = False
        self._closed = False

    @classmethod
    def create(
        cls,
        path: str | os.PathLike[str],
        *,
        embedding_function: EmbeddingFunction | None = None,
        model: str = "hashing",
        embedding_normalization: EmbeddingNormalization | None = None,
        metadata: JsonObject | None = None,
        overwrite: bool = False,
    ) -> VeraDocument:
        """Create a new empty ``.vera`` archive at ``path``.

        Args:
            path: Destination file path.
            embedding_function: Custom embedder. When omitted, ``model`` selects
                the default embedder.
            model: Default embedding model name (for example ``"hashing"``).
            embedding_normalization: Stored-vector normalization policy. When
                omitted, use the embedder's declared policy or ``"unknown"``.
            metadata: Caller-controlled JSON metadata stored in the archive.
            overwrite: When ``False`` (default), raise :class:`FileExistsError`
                if ``path`` already exists.

        Returns:
            A write-mode database handle.

        Raises:
            FileExistsError: When the target exists and ``overwrite`` is false.
        """
        target = Path(path)
        if target.exists() and not overwrite:
            raise FileExistsError(str(target))
        embedder = embedding_function or get_embedder(model)
        embedder_normalization = _embedding_normalization(getattr(embedder, "normalization", None))
        normalization = _embedding_normalization(
            embedding_normalization,
            default=embedder_normalization,
        )
        if (
            normalization != "unknown"
            and embedder_normalization != "unknown"
            and normalization != embedder_normalization
        ):
            raise ValueError(
                "embedding normalization "
                f"{normalization!r} does not match embedding function "
                f"normalization {embedder_normalization!r}"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        conn: sqlite3.Connection | None = None
        try:
            conn = sqlite3.connect(temporary)
            conn.row_factory = sqlite3.Row
            create_schema(conn)
            now = _utc_now()
            values = {
                "format_name": "VERA",
                "format_version": FORMAT_VERSION,
                "created_at": now,
                "created_by": "vera-doc",
                "creator_library": f"vera-doc/{_package_version()}",
                "default_embedding_model": embedder.model_name,
                "default_embedding_dimension": str(embedder.dimension),
                "default_embedding_normalization": normalization,
                "archive_metadata": metadata_to_json(metadata or {}),
            }
            conn.executemany(
                "INSERT INTO vera_metadata(key, value) VALUES (?, ?)",
                values.items(),
            )
            conn.commit()
            conn.close()
            conn = None
            os.replace(temporary, target)
        except BaseException:
            if conn is not None:
                conn.close()
            temporary.unlink(missing_ok=True)
            raise
        return cls.open(
            target,
            mode="write",
            embedding_function=embedder,
        )

    @classmethod
    def open(
        cls,
        path: str | os.PathLike[str],
        *,
        mode: OpenMode = "read",
        embedding_function: EmbeddingFunction | None = None,
    ) -> VeraDocument:
        """Open an existing ``.vera`` archive.

        Args:
            path: Path to an existing archive.
            mode: ``"read"`` (default) opens SQLite read-only; ``"write"`` allows
                mutations.
            embedding_function: Embedder used for write-mode searches and record
                writes. When omitted in write mode, the model recorded in the
                archive is used.

        Returns:
            A database handle.

        Raises:
            FileNotFoundError: When ``path`` does not exist.
            ValueError: When the archive format version is unsupported or the
                embedder dimension does not match the archive.
        """
        target = Path(path)
        if not target.is_file():
            raise FileNotFoundError(str(target))
        if mode not in {"read", "write"}:
            raise ValueError("mode must be 'read' or 'write'")
        if mode == "read":
            uri = f"{target.resolve().as_uri()}?mode=ro"
            conn = sqlite3.connect(uri, uri=True)
        else:
            conn = sqlite3.connect(target)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            try:
                metadata_rows = conn.execute("SELECT key, value FROM vera_metadata").fetchall()
            except sqlite3.OperationalError as exc:
                if "no such table" in str(exc).lower():
                    raise ValueError("Missing required table: vera_metadata") from exc
                raise
            stored = {row["key"]: row["value"] for row in metadata_rows}
            stored_version = stored.get("format_version")
            if stored_version is not None and stored_version != FORMAT_VERSION:
                raise ValueError(
                    f"VeraDocument requires format {FORMAT_VERSION}; found {stored_version}"
                )
            if embedding_function is None and mode == "write":
                embedding_function = get_embedder(stored.get("default_embedding_model", "hashing"))
            if embedding_function is not None:
                expected = int(stored["default_embedding_dimension"])
                if embedding_function.dimension != expected:
                    raise ValueError(
                        "embedding function dimension "
                        f"{embedding_function.dimension} does not match database dimension {expected}"
                    )
                stored_normalization = _embedding_normalization(
                    stored.get("default_embedding_normalization")
                )
                embedder_normalization = _embedding_normalization(
                    getattr(embedding_function, "normalization", None)
                )
                if (
                    stored_normalization != "unknown"
                    and embedder_normalization != "unknown"
                    and embedder_normalization != stored_normalization
                ):
                    raise ValueError(
                        "embedding function normalization "
                        f"{embedder_normalization!r} does not match database "
                        f"normalization {stored_normalization!r}"
                    )
            return cls(
                target,
                conn,
                mode=mode,
                embedding_function=embedding_function,
            )
        except BaseException:
            conn.close()
            raise

    @property
    def mode(self) -> OpenMode:
        return self._mode

    @property
    def metadata(self) -> dict[str, Any]:
        """Caller-controlled archive metadata as a mutable dict."""
        value = self._metadata_values().get("archive_metadata", "{}")
        return thaw_json(metadata_from_json(value))

    def set_metadata(self, metadata: JsonObject) -> None:
        """Replace caller-controlled archive metadata.

        Args:
            metadata: JSON-compatible mapping stored in the archive header.

        Raises:
            ReadOnlyError: When the database is opened read-only.
        """
        self._ensure_writable()
        with self._write_scope():
            self._conn.execute(
                "UPDATE vera_metadata SET value = ? WHERE key = 'archive_metadata'",
                (metadata_to_json(metadata),),
            )

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
                self._conn.execute(
                    "DELETE FROM chunks_fts WHERE chunk_id = ?",
                    (record.id,),
                )
                self._conn.execute(
                    "INSERT INTO chunks_fts(chunk_id, text) VALUES (?, ?)",
                    (record.id, record.text),
                )
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
        params: list[Any] = []
        if requested is not None:
            placeholders = ",".join("?" for _ in requested)
            sql += f" WHERE c.chunk_id IN ({placeholders})"
            params.extend(requested)
        sql += " ORDER BY c.rowid"
        rows = self._conn.execute(sql, params).fetchall()
        records = [self._row_to_record(row) for row in rows]
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
                self._conn.execute(
                    "DELETE FROM chunks_fts WHERE chunk_id = ?",
                    (record.id,),
                )
                self._conn.execute(
                    "DELETE FROM chunks WHERE chunk_id = ?",
                    (record.id,),
                )
        return len(records)

    def search(
        self,
        text: str | None = None,
        *,
        vector: Sequence[float] | None = None,
        mode: SearchMode = "hybrid",
        where: Mapping[str, Any] | None = None,
        top_k: int = 10,
        context_chunks: int = 0,
    ) -> list[QueryResult]:
        """Search chunk records.

        Args:
            text: Query string for semantic or keyword search. Required unless
                ``vector`` is supplied for semantic mode.
            vector: Pre-computed query vector for semantic search.
            mode: ``"hybrid"`` (default), ``"semantic"``, or ``"keyword"``.
            where: Exact equality filter on top-level metadata keys.
            top_k: Maximum number of results to return.
            context_chunks: Number of adjacent stored chunks to include.

        Returns:
            Ranked :class:`~vera_doc.models.QueryResult` objects.
        """
        self._ensure_open()
        if mode not in {"semantic", "keyword", "hybrid"}:
            raise ValueError("mode must be semantic, keyword, or hybrid")
        if top_k < 0:
            raise ValueError("top_k must be non-negative")
        if top_k > _MAX_TOP_K:
            raise ValueError(f"top_k must be at most {_MAX_TOP_K}")
        if context_chunks < 0:
            raise ValueError("context_chunks must be non-negative")
        if top_k == 0:
            return []
        if mode in {"keyword", "hybrid"} and not text:
            raise ValueError(f"{mode} search requires text")
        semantic: dict[str, float] = {}
        keyword: dict[str, float] = {}
        if mode in {"semantic", "hybrid"}:
            query_vector = self._query_vector(text=text, vector=vector)
            semantic = self._semantic_scores(query_vector)
        if mode in {"keyword", "hybrid"}:
            keyword = self._keyword_scores(text or "")
        if mode == "semantic":
            combined = semantic
        elif mode == "keyword":
            combined = keyword
        else:
            semantic_norm = _normalize_scores(semantic)
            keyword_norm = _normalize_scores(keyword)
            combined = {
                record_id: 0.5 * semantic_norm.get(record_id, 0.0)
                + 0.5 * keyword_norm.get(record_id, 0.0)
                for record_id in semantic.keys() | keyword.keys()
            }
        matching_ids = self._chunk_ids(where)
        ranked = sorted(
            (
                (record_id, score)
                for record_id, score in combined.items()
                if record_id in matching_ids
            ),
            key=lambda item: (-item[1], item[0]),
        )[:top_k]
        needed = [record_id for record_id, _ in ranked]
        ordered_ids: list[str] = []
        if context_chunks and needed:
            ordered_ids = self._chunk_ids_in_order()
            positions = {chunk_id: index for index, chunk_id in enumerate(ordered_ids)}
            extra: list[str] = []
            for record_id in needed:
                position = positions.get(record_id)
                if position is None:
                    continue
                extra.extend(ordered_ids[max(0, position - context_chunks) : position])
                extra.extend(ordered_ids[position + 1 : position + context_chunks + 1])
            needed = list(dict.fromkeys([*needed, *extra]))
        records = {record.id: record for record in self.get(needed)}
        results = [
            QueryResult(
                record=records[record_id],
                score=float(score),
                semantic_score=semantic.get(record_id),
                keyword_score=keyword.get(record_id),
            )
            for record_id, score in ranked
            if record_id in records
        ]
        if context_chunks and ordered_ids:
            by_id = records
            positions = {chunk_id: index for index, chunk_id in enumerate(ordered_ids)}
            results = [
                replace(
                    result,
                    before=tuple(
                        by_id[chunk_id]
                        for chunk_id in ordered_ids[
                            max(0, positions[result.record.id] - context_chunks) : positions[
                                result.record.id
                            ]
                        ]
                        if chunk_id in by_id
                    ),
                    after=tuple(
                        by_id[chunk_id]
                        for chunk_id in ordered_ids[
                            positions[result.record.id] + 1 : positions[result.record.id]
                            + context_chunks
                            + 1
                        ]
                        if chunk_id in by_id
                    ),
                )
                for result in results
            ]
        return results

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
            ``ids`` is provided.
        """
        self._ensure_open()
        requested = tuple(ids) if ids is not None else None
        if requested is not None and not requested:
            return []
        sql = """
            SELECT attachment_id, mime_type, filename, hash, metadata_json
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

    def inspect(self) -> dict[str, Any]:
        """Return archive metadata and record counts.

        Returns:
            A dict with ``path``, ``format_version``, ``embedding_model``,
            ``chunks``, ``attachments``, and related fields.
        """
        self._ensure_open()
        metadata = self._metadata_values()
        archive_metadata = self.metadata
        try:
            archive_size = self.path.stat().st_size
        except OSError:
            archive_size = None
        return {
            **archive_metadata,
            "path": str(self.path),
            "archive_size_bytes": archive_size,
            "format_name": metadata.get("format_name"),
            "format_version": metadata.get("format_version"),
            "created_at": metadata.get("created_at"),
            "embedding_model": metadata.get("default_embedding_model"),
            "default_embedding_model": metadata.get("default_embedding_model"),
            "embedding_dimension": int(metadata.get("default_embedding_dimension", 0)),
            "default_embedding_dimension": int(metadata.get("default_embedding_dimension", 0)),
            "embedding_normalization": metadata.get("default_embedding_normalization", "unknown"),
            "default_embedding_normalization": metadata.get(
                "default_embedding_normalization", "unknown"
            ),
            "chunks": self._conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
            "attachments": self._conn.execute("SELECT COUNT(*) FROM attachments").fetchone()[0],
            "pages": archive_metadata.get("page_count", 0),
            "source": archive_metadata.get("source_file_name"),
            "metadata": archive_metadata,
        }

    def validate(self) -> dict[str, Any]:
        """Check archive integrity.

        Returns:
            A report dict with an ``ok`` boolean and an ``issues`` list.
        """
        self._ensure_open()
        return validate_document(self._conn)

    @contextmanager
    def transaction(self) -> Iterator[VeraDocument]:
        """Run a batch of writes in a single SQLite transaction.

        Yields:
            This database handle for use inside the ``with`` block.

        Raises:
            RuntimeError: When nested transactions are attempted.
            ReadOnlyError: When the database is opened read-only.
        """
        self._ensure_writable()
        if self._transaction_active:
            raise RuntimeError("nested transactions are not supported")
        self._conn.execute("BEGIN")
        self._transaction_active = True
        try:
            yield self
        except BaseException:
            self._conn.rollback()
            raise
        else:
            self._conn.commit()
        finally:
            self._transaction_active = False

    @contextmanager
    def _write_scope(self) -> Iterator[None]:
        if self._transaction_active:
            yield
            return
        try:
            yield
        except BaseException:
            self._conn.rollback()
            raise
        else:
            self._conn.commit()

    def _row_to_record(self, row: sqlite3.Row) -> ChunkRecord:
        refs = tuple(
            AttachmentRef(
                attachment_id=ref["attachment_id"],
                role=ref["role"] or None,
            )
            for ref in self._conn.execute(
                """
                SELECT attachment_id, role FROM chunk_attachments
                WHERE chunk_id = ? ORDER BY attachment_id, role
                """,
                (row["chunk_id"],),
            )
        )
        return ChunkRecord(
            id=row["chunk_id"],
            text=row["text"],
            metadata=metadata_from_json(row["metadata_json"]),
            vector=tuple(float(value) for value in deserialize_vector(row["vector"])),
            attachments=refs,
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

    def _query_vector(
        self,
        *,
        text: str | None,
        vector: Sequence[float] | None,
    ) -> np.ndarray:
        expected = int(self._metadata_values()["default_embedding_dimension"])
        if vector is None:
            if text is None:
                raise ValueError("semantic search requires text or vector")
            embedder = self._embedding_function
            if embedder is None:
                model_name = self._metadata_values()["default_embedding_model"]
                embedder = get_embedder(model_name)
            query = np.asarray(embedder.embed([text])[0], dtype=np.float32)
        else:
            query = np.asarray(vector, dtype=np.float32)
        if query.ndim != 1 or query.size != expected:
            raise ValueError(
                f"query vector dimension {query.size} does not match database dimension {expected}"
            )
        if not np.isfinite(query).all():
            raise ValueError("query vector must contain only finite numbers")
        return query

    def _semantic_scores(self, query: np.ndarray) -> dict[str, float]:
        query_norm = float(np.linalg.norm(query))
        if query_norm == 0:
            return {}
        scores: dict[str, float] = {}
        for row in self._conn.execute("SELECT chunk_id, vector, model_dimension FROM embeddings"):
            vector = deserialize_vector(row["vector"])
            denominator = float(np.linalg.norm(vector)) * query_norm
            scores[row["chunk_id"]] = (
                float(np.dot(vector, query) / denominator) if denominator else 0.0
            )
        return scores

    def _keyword_scores(self, text: str) -> dict[str, float]:
        sql = """
            SELECT chunk_id, bm25(chunks_fts) AS rank
            FROM chunks_fts
            WHERE chunks_fts MATCH ?
        """
        rows = execute_fts(self._conn, sql, text)
        if not rows:
            fallback = safe_fts_query(text)
            if fallback:
                rows = execute_fts(self._conn, sql, fallback)
        return {row["chunk_id"]: -float(row["rank"]) for row in rows}

    def _chunk_ids(self, where: Mapping[str, Any] | None) -> set[str]:
        if not where:
            return {str(row[0]) for row in self._conn.execute("SELECT chunk_id FROM chunks")}
        matching: set[str] = set()
        for row in self._conn.execute("SELECT chunk_id, metadata_json FROM chunks"):
            metadata = thaw_json(metadata_from_json(row["metadata_json"]))
            if all(metadata.get(key) == expected for key, expected in where.items()):
                matching.add(str(row["chunk_id"]))
        return matching

    def _chunk_ids_in_order(self) -> list[str]:
        return [
            str(row[0]) for row in self._conn.execute("SELECT chunk_id FROM chunks ORDER BY rowid")
        ]

    def _metadata_values(self) -> dict[str, str]:
        return {
            row["key"]: row["value"]
            for row in self._conn.execute("SELECT key, value FROM vera_metadata")
        }

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("database is closed")

    def _ensure_writable(self) -> None:
        self._ensure_open()
        if self._mode != "write":
            raise ReadOnlyError("database is read-only")

    def close(self) -> None:
        """Close the database connection."""
        if not self._closed:
            if self._transaction_active:
                self._conn.rollback()
                self._transaction_active = False
            self._conn.close()
            self._closed = True

    def __enter__(self) -> VeraDocument:
        self._ensure_open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
