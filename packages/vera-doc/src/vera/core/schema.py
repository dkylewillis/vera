import sqlite3

FORMAT_VERSION = "0.2"
REQUIRED_METADATA_KEYS = [
    "format_name",
    "format_version",
    "created_at",
    "created_by",
    "creator_library",
    "default_embedding_model",
    "default_embedding_dimension",
    "archive_metadata",
]


def create_schema(conn: sqlite3.Connection) -> None:
    """Create the chunk-oriented VERA 0.2 storage schema."""
    conn.executescript(
        """
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS vera_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id TEXT PRIMARY KEY,
            text TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS embeddings (
            chunk_id TEXT PRIMARY KEY,
            model_name TEXT NOT NULL,
            model_dimension INTEGER NOT NULL,
            vector BLOB NOT NULL,
            vector_format TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS attachments (
            attachment_id TEXT PRIMARY KEY,
            mime_type TEXT NOT NULL,
            filename TEXT,
            data BLOB NOT NULL,
            hash TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS chunk_attachments (
            chunk_id TEXT NOT NULL,
            attachment_id TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (chunk_id, attachment_id, role),
            FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id) ON DELETE CASCADE,
            FOREIGN KEY (attachment_id) REFERENCES attachments(attachment_id) ON DELETE RESTRICT
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            chunk_id UNINDEXED,
            text
        );
        CREATE INDEX IF NOT EXISTS idx_chunk_attachments_attachment
            ON chunk_attachments(attachment_id);
        """
    )
    conn.commit()
