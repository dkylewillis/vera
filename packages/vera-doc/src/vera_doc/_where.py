"""Exact-equality and IN filters for top-level metadata keys."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import (
    METADATA_DOCUMENT_ID,
    METADATA_HEADING_PATH,
    METADATA_PAGE_END,
    METADATA_PAGE_START,
    METADATA_SOURCE_FILENAME,
)

INDEX_CITATION_COLUMNS = frozenset(
    {
        METADATA_DOCUMENT_ID,
        METADATA_SOURCE_FILENAME,
        METADATA_PAGE_START,
        METADATA_PAGE_END,
        METADATA_HEADING_PATH,
    }
)

CHUNK_METADATA_FILTER_REASON = "chunk metadata filter not in collection index"


def metadata_value_matches(actual: Any, expected: Any) -> bool:
    """Return whether ``actual`` satisfies a scalar equality or list IN clause."""
    if isinstance(expected, (list, tuple, set)):
        return any(actual == item for item in expected)
    return actual == expected


def metadata_matches(
    metadata: Mapping[str, Any] | None,
    where: Mapping[str, Any] | None,
) -> bool:
    """AND across keys; a list/tuple/set value is IN, a scalar is ``==``.

    Missing keys fail the predicate (``dict.get`` yields ``None``). An empty
    or omitted ``where`` matches every record. List-valued *stored* metadata
    is not an IN clause; IN applies to the filter value only.
    """
    if not where:
        return True
    data = metadata or {}
    return all(
        metadata_value_matches(data.get(key), expected) for key, expected in where.items()
    )
