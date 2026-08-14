from __future__ import annotations

import os
import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from ._document_attachments import _DocumentAttachmentsMixin
from ._document_records import _DocumentRecordsMixin
from ._document_search import _DocumentSearchMixin
from ._errors import DuplicateRecordError, ReadOnlyError, RecordNotFoundError
from ._fts import execute_fts, is_fts_syntax_error, safe_fts_query
from ._schema import FORMAT_VERSION, create_schema
from ._util import (
    _MAX_TOP_K as _MAX_TOP_K,
)
from ._util import (
    EmbeddingNormalization,
    OpenMode,
    SearchMode,
    _embedding_normalization,
    _package_version,
    _utc_now,
)
from .embeddings import EmbeddingFunction, get_embedder
from .models import JsonObject, metadata_from_json, metadata_to_json, thaw_json
from .validation import validate_document

__all__ = [
    "DuplicateRecordError",
    "EmbeddingNormalization",
    "OpenMode",
    "ReadOnlyError",
    "RecordNotFoundError",
    "SearchMode",
    "VeraDocument",
    "execute_fts",
    "is_fts_syntax_error",
    "safe_fts_query",
]


class VeraDocument(_DocumentRecordsMixin, _DocumentSearchMixin, _DocumentAttachmentsMixin):
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

    def format_metadata(self) -> dict[str, str]:
        """Return the archive format header as a key/value mapping."""
        self._ensure_open()
        return self._metadata_values()

    def iter_raw_chunks(self) -> Iterator[dict[str, Any]]:
        """Yield chunk text, metadata, model name, dimension, and raw vector bytes.

        This is the bulk-read path used by the library index builder. It avoids
        constructing :class:`ChunkRecord` objects and does not load attachments.
        """
        self._ensure_open()
        rows = self._conn.execute(
            """
            SELECT c.chunk_id, c.text, c.metadata_json,
                   e.model_name, e.model_dimension, e.vector
            FROM chunks c
            JOIN embeddings e ON e.chunk_id = c.chunk_id
            ORDER BY c.rowid
            """
        )
        for row in rows:
            yield {
                "chunk_id": str(row["chunk_id"]),
                "text": str(row["text"]),
                "metadata_json": str(row["metadata_json"]),
                "model_name": str(row["model_name"]),
                "model_dimension": int(row["model_dimension"]),
                "vector": bytes(row["vector"]),
            }

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
