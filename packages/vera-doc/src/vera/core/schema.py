import sqlite3

FORMAT_VERSION = "0.2"
LEGACY_FORMAT_VERSION = "0.1"
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
LEGACY_REQUIRED_METADATA_KEYS = [
    key for key in REQUIRED_METADATA_KEYS if key != "archive_metadata"
] + [
    "source_file_name",
    "source_file_hash",
    "source_mime_type",
    "chunking_strategy",
    "parser_name",
    "parser_version",
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


def create_legacy_schema(conn: sqlite3.Connection) -> None:
    """Create the VERA 0.1 document schema for compatibility tooling."""
    conn.executescript(
        """
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS vera_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS documents (
            document_id TEXT PRIMARY KEY,
            title TEXT,
            source_filename TEXT,
            source_mime_type TEXT,
            source_hash TEXT,
            page_count INTEGER,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS pages (
            page_id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            page_number INTEGER NOT NULL,
            width REAL,
            height REAL,
            text TEXT,
            FOREIGN KEY (document_id) REFERENCES documents(document_id)
        );
        CREATE TABLE IF NOT EXISTS blocks (
            block_id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            page_id TEXT,
            page_number INTEGER,
            block_type TEXT,
            text TEXT,
            bbox_json TEXT,
            heading_level INTEGER,
            sort_order INTEGER,
            FOREIGN KEY (document_id) REFERENCES documents(document_id),
            FOREIGN KEY (page_id) REFERENCES pages(page_id)
        );
        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            page_start INTEGER,
            page_end INTEGER,
            heading_path TEXT,
            text TEXT NOT NULL,
            token_count INTEGER,
            chunk_hash TEXT,
            sort_order INTEGER,
            FOREIGN KEY (document_id) REFERENCES documents(document_id)
        );
        CREATE TABLE IF NOT EXISTS chunk_blocks (
            chunk_id TEXT NOT NULL,
            block_id TEXT NOT NULL,
            PRIMARY KEY (chunk_id, block_id),
            FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id),
            FOREIGN KEY (block_id) REFERENCES blocks(block_id)
        );
        CREATE TABLE IF NOT EXISTS embeddings (
            embedding_id TEXT PRIMARY KEY,
            chunk_id TEXT NOT NULL,
            model_name TEXT NOT NULL,
            model_dimension INTEGER NOT NULL,
            vector BLOB NOT NULL,
            vector_format TEXT NOT NULL,
            created_at TEXT,
            FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id)
        );
        CREATE TABLE IF NOT EXISTS assets (
            asset_id TEXT PRIMARY KEY,
            document_id TEXT,
            asset_type TEXT NOT NULL,
            mime_type TEXT,
            filename TEXT,
            data BLOB,
            hash TEXT,
            FOREIGN KEY (document_id) REFERENCES documents(document_id)
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            chunk_id UNINDEXED,
            text,
            heading_path
        );
        CREATE INDEX IF NOT EXISTS idx_pages_doc ON pages(document_id, page_number);
        CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(document_id, sort_order);
        CREATE INDEX IF NOT EXISTS idx_embeddings_chunk ON embeddings(chunk_id);
        """
    )
    conn.commit()
