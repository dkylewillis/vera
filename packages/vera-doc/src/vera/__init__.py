"""VERA — Vector-Embedded Retrieval Archive."""

from .collection import (
    VeraCollectionIndex,
    build_library_index,
    library_index_status,
    update_library_index,
)
from .corpus import CorpusSearchResult, VeraCorpus
from .core.embedder_descriptors import (
    EmbedderCapabilities,
    EmbedderDescriptor,
    EmbedderField,
    EmbedderFieldChoice,
    EmbedderPreflightResult,
    EmbeddingModelInfo,
)
from .core.embedder_options import EmbedderOptions
from .core.embeddings import (
    EmbeddingFunction,
    UnknownEmbeddingModelError,
    clear_embedder_cache,
    describe_embedder,
    get_embedder,
    list_embedding_models,
    list_embedding_provider_descriptors,
    list_embedding_providers,
    preflight_embedder,
    register_embedder,
    register_embedder_descriptor,
    register_embedder_models,
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
    "EmbedderOptions",
    "EmbedderDescriptor",
    "EmbedderField",
    "EmbedderFieldChoice",
    "EmbedderCapabilities",
    "EmbeddingModelInfo",
    "EmbedderPreflightResult",
    "EmbeddingNormalization",
    "UnknownEmbeddingModelError",
    "get_embedder",
    "register_embedder",
    "register_embedder_descriptor",
    "register_embedder_models",
    "describe_embedder",
    "list_embedding_providers",
    "list_embedding_provider_descriptors",
    "list_embedding_models",
    "preflight_embedder",
    "clear_embedder_cache",
    "ChunkRecord",
    "AttachmentRecord",
    "AttachmentRef",
    "QueryResult",
    "DuplicateRecordError",
    "RecordNotFoundError",
    "ReadOnlyError",
]
