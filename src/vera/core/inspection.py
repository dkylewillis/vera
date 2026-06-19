from __future__ import annotations

import sqlite3
from typing import Any


def inspect_document(conn: sqlite3.Connection, path: str) -> dict[str, Any]:
    """Return metadata and summary counts for a VERA document."""
    metadata = {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM vera_metadata")}
    doc = conn.execute("SELECT * FROM documents LIMIT 1").fetchone()
    metadata.update(
        {
            "file": path,
            "source": doc["source_filename"] if doc else None,
            "pages": conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0],
            "chunks": conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
            "embeddings": conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0],
        }
    )
    return metadata
