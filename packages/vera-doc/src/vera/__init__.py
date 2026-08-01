"""VERA — Vector-Embedded Retrieval Archive."""

from .collection import (
    VeraCollectionIndex,
    build_library_index,
    library_index_status,
    update_library_index,
)
from .corpus import CorpusSearchResult, VeraCorpus
from .database import (
    DuplicateRecordError,
    EmbeddingFunction,
    ReadOnlyError,
    RecordNotFoundError,
    VeraDatabase,
)
from .document import VeraDocument, SearchResult, SourceDocument
from .models import AttachmentRecord, AttachmentRef, ChunkRecord, QueryResult

__all__ = [
    "VeraDocument",
    "SearchResult",
    "SourceDocument",
    "VeraCorpus",
    "CorpusSearchResult",
    "VeraCollectionIndex",
    "build_library_index",
    "update_library_index",
    "library_index_status",
    "VeraDatabase",
    "EmbeddingFunction",
    "ChunkRecord",
    "AttachmentRecord",
    "AttachmentRef",
    "QueryResult",
    "DuplicateRecordError",
    "RecordNotFoundError",
    "ReadOnlyError",
]
