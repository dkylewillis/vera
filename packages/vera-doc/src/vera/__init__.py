"""VERA — Vector-Embedded Retrieval Archive."""

from .collection import (
    VeraCollectionIndex,
    build_library_index,
    library_index_status,
    update_library_index,
)
from .corpus import CorpusSearchResult, VeraCorpus
from .core.embeddings import (
    EmbeddingFunction,
    UnknownEmbeddingModelError,
    clear_embedder_cache,
    get_embedder,
    list_embedding_providers,
    register_embedder,
)
from .document import (
    DuplicateRecordError,
    EmbeddingNormalization,
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
    "EmbeddingNormalization",
    "UnknownEmbeddingModelError",
    "get_embedder",
    "register_embedder",
    "list_embedding_providers",
    "clear_embedder_cache",
    "ChunkRecord",
    "AttachmentRecord",
    "AttachmentRef",
    "QueryResult",
    "DuplicateRecordError",
    "RecordNotFoundError",
    "ReadOnlyError",
]
