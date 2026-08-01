"""VERA — Vector-Embedded Retrieval Archive."""

from .collection import (
    VeraCollectionIndex,
    build_library_index,
    library_index_status,
    update_library_index,
)
from .corpus import CorpusSearchResult, VeraCorpus
from .document import (
    DuplicateRecordError,
    EmbeddingFunction,
    ReadOnlyError,
    RecordNotFoundError,
    VeraDocument,
)
from .models import AttachmentRecord, AttachmentRef, ChunkRecord, QueryResult

__all__ = [
    "VeraDocument",
    "VeraCorpus",
    "CorpusSearchResult",
    "VeraCollectionIndex",
    "build_library_index",
    "update_library_index",
    "library_index_status",
    "EmbeddingFunction",
    "ChunkRecord",
    "AttachmentRecord",
    "AttachmentRef",
    "QueryResult",
    "DuplicateRecordError",
    "RecordNotFoundError",
    "ReadOnlyError",
]
