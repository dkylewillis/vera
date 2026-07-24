"""VERA — Vector-Embedded Retrieval Archive."""

from .collection import (
    VeraCollectionIndex,
    build_library_index,
    library_index_status,
    update_library_index,
)
from .convert import batch_convert, convert
from .corpus import CorpusSearchResult, VeraCorpus
from .document import VeraDocument, SearchResult, SourceDocument

__all__ = [
    "convert",
    "batch_convert",
    "VeraDocument",
    "SearchResult",
    "SourceDocument",
    "VeraCorpus",
    "CorpusSearchResult",
    "VeraCollectionIndex",
    "build_library_index",
    "update_library_index",
    "library_index_status",
]
