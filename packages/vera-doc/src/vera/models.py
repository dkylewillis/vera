from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

JsonObject = Mapping[str, Any]


def _freeze_json(value: Any, *, path: str = "metadata") -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} contains a non-finite number")
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} keys must be strings")
            frozen[key] = _freeze_json(item, path=f"{path}.{key}")
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(
            _freeze_json(item, path=f"{path}[{index}]") for index, item in enumerate(value)
        )
    raise TypeError(f"{path} contains a non-JSON value: {type(value).__name__}")


def thaw_json(value: Any) -> Any:
    """Return a JSON-serializable copy of a frozen metadata value."""
    if isinstance(value, Mapping):
        return {key: thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_json(item) for item in value]
    return value


def metadata_to_json(metadata: JsonObject) -> str:
    return json.dumps(
        thaw_json(metadata),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def metadata_from_json(value: str | None) -> JsonObject:
    parsed = json.loads(value or "{}")
    if not isinstance(parsed, dict):
        raise ValueError("metadata JSON must contain an object")
    return _freeze_json(parsed)


def _validate_id(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if "\x00" in normalized:
        raise ValueError(f"{field_name} must not contain NUL characters")
    return normalized


@dataclass(frozen=True)
class AttachmentRef:
    """Reference from a chunk to a stored attachment.

    Attributes:
        attachment_id: ID of the stored attachment.
        role: Optional semantic role (for example ``"source"`` or ``"figure"``).
    """

    attachment_id: str
    role: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "attachment_id",
            _validate_id(self.attachment_id, "attachment_id"),
        )
        if self.role is not None:
            object.__setattr__(self, "role", _validate_id(self.role, "role"))


@dataclass(frozen=True)
class ChunkRecord:
    """Immutable searchable chunk supplied by the caller.

    Attributes:
        id: Stable identifier within the archive.
        text: Non-empty searchable content.
        metadata: JSON-compatible citation and filter fields.
        vector: Optional pre-computed embedding. When omitted, the configured
            embedding function embeds ``text`` on write.
        attachments: Links to stored binary attachments.

    Raises:
        ValueError: When ``id`` or ``text`` is empty or ``vector`` is invalid.
        TypeError: When ``metadata`` contains non-JSON values.
    """

    id: str
    text: str
    metadata: JsonObject = field(default_factory=dict)
    vector: Sequence[float] | None = None
    attachments: tuple[AttachmentRef, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _validate_id(self.id, "id"))
        if not isinstance(self.text, str):
            raise TypeError("text must be a string")
        if not self.text.strip():
            raise ValueError("text must not be empty")
        object.__setattr__(self, "metadata", _freeze_json(self.metadata))
        if self.vector is not None:
            vector = tuple(float(item) for item in self.vector)
            if not vector:
                raise ValueError("vector must not be empty")
            if not all(math.isfinite(item) for item in vector):
                raise ValueError("vector must contain only finite numbers")
            object.__setattr__(self, "vector", vector)
        refs = tuple(self.attachments)
        if len({(ref.attachment_id, ref.role) for ref in refs}) != len(refs):
            raise ValueError("attachment references must be unique")
        object.__setattr__(self, "attachments", refs)


@dataclass(frozen=True)
class AttachmentRecord:
    """Opaque binary attachment stored in a ``.vera`` archive.

    Attributes:
        id: Stable attachment identifier.
        data: Raw attachment bytes.
        media_type: MIME type (for example ``"application/pdf"``).
        filename: Optional original filename.
        checksum: Optional SHA-256 hex digest. Computed automatically when
            omitted; validated when supplied.
        metadata: JSON-compatible attachment metadata.

    Raises:
        ValueError: When ``checksum`` does not match ``data``.
    """

    id: str
    data: bytes
    media_type: str
    filename: str | None = None
    checksum: str | None = None
    metadata: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _validate_id(self.id, "id"))
        if not isinstance(self.data, bytes):
            raise TypeError("data must be bytes")
        object.__setattr__(
            self,
            "media_type",
            _validate_id(self.media_type, "media_type"),
        )
        if self.filename is not None and not isinstance(self.filename, str):
            raise TypeError("filename must be a string or None")
        digest = hashlib.sha256(self.data).hexdigest()
        if self.checksum is not None and self.checksum.lower() != digest:
            raise ValueError("checksum does not match attachment data")
        object.__setattr__(self, "checksum", digest)
        object.__setattr__(self, "metadata", _freeze_json(self.metadata))


@dataclass(frozen=True)
class QueryResult:
    """Ranked search hit from :meth:`~vera.document.VeraDocument.search`.

    Attributes:
        record: Matching chunk record.
        score: Combined relevance score for the selected mode.
        semantic_score: Raw semantic score, when applicable.
        keyword_score: Raw keyword score, when applicable.
    """

    record: ChunkRecord
    score: float
    semantic_score: float | None = None
    keyword_score: float | None = None
    before: tuple[ChunkRecord, ...] = ()
    after: tuple[ChunkRecord, ...] = ()

    @property
    def chunk_id(self) -> str:
        return self.record.id

    @property
    def text(self) -> str:
        return self.record.text

    @property
    def page_start(self) -> int | None:
        value = self.record.metadata.get("page_start")
        return value if isinstance(value, int) else None

    @property
    def page_end(self) -> int | None:
        value = self.record.metadata.get("page_end")
        return value if isinstance(value, int) else None

    @property
    def heading_path(self) -> str | None:
        value = self.record.metadata.get("heading_path")
        return value if isinstance(value, str) else None

    @property
    def source_filename(self) -> str | None:
        value = self.record.metadata.get("source_filename")
        return value if isinstance(value, str) else None

    @property
    def document_id(self) -> str | None:
        value = self.record.metadata.get("document_id")
        return value if isinstance(value, str) else None

    @property
    def before_chunks(self) -> list[dict[str, Any]]:
        return [_record_dict(record) for record in self.before]

    @property
    def after_chunks(self) -> list[dict[str, Any]]:
        return [_record_dict(record) for record in self.after]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of this result."""
        data: dict[str, Any] = {
            "chunk_id": self.record.id,
            "score": self.score,
            "text": self.record.text,
            "metadata": thaw_json(self.record.metadata),
        }
        if self.semantic_score is not None:
            data["semantic_score"] = self.semantic_score
        if self.keyword_score is not None:
            data["keyword_score"] = self.keyword_score
        if self.before or self.after:
            data["before_chunks"] = [_record_dict(record) for record in self.before]
            data["after_chunks"] = [_record_dict(record) for record in self.after]
        return data


def _record_dict(record: ChunkRecord) -> dict[str, Any]:
    return {
        "chunk_id": record.id,
        "text": record.text,
        "metadata": thaw_json(record.metadata),
    }
