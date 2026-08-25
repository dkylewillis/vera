"""Shared private helpers for archive I/O and search limits."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from typing import Literal, cast

OpenMode = Literal["read", "write"]
SearchMode = Literal["semantic", "keyword", "hybrid"]
EmbeddingNormalization = Literal["l2", "none", "unknown"]
_EMBEDDING_NORMALIZATIONS = frozenset({"l2", "none", "unknown"})
_L2_NORMALIZATION_RTOL = 1e-4
_L2_NORMALIZATION_ATOL = 1e-6
_MAX_TOP_K = 10_000
# SQLite rejects statements with more host variables than
# SQLITE_LIMIT_VARIABLE_NUMBER, which is 999 on builds older than 3.32 and
# 32766 on current ones. Batch id lists well below the lower bound so a large
# archive cannot outgrow whichever SQLite the caller happens to link.
_SQL_VARIABLE_BATCH = 500
_ATTACHMENT_WRITE_CHUNK = 8 * 1024 * 1024


def _batched(values: Sequence[str], size: int) -> Iterator[tuple[str, ...]]:
    for start in range(0, len(values), size):
        yield tuple(values[start : start + size])


def _package_version() -> str:
    try:
        return package_version("vera-doc")
    except PackageNotFoundError:
        return "0.3.1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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
