# VERA Format Specification

**Version:** 0.2 (draft)  
**Status:** Experimental — the schema may change before 1.0  
**License:** Apache-2.0

VERA 0.2 is a portable, single-file embedded vector database. A `.vera` file
stores ready-made text chunks, one vector per chunk, a keyword index,
JSON-compatible metadata, and optional opaque attachments. Extraction,
parsing, OCR, cleaning, and chunking are deliberately outside this format.

The key words MUST, SHOULD, and MAY are interpreted as described in RFC 2119.

## 1. Container

- A VERA file MUST be a valid SQLite 3 database.
- The recommended extension is `.vera`.
- The database MUST pass `PRAGMA integrity_check`.
- Readers MUST ignore unknown tables, columns, and metadata keys.
- Writers MAY add extension tables prefixed with `x_`.
- Foreign-key enforcement MUST be enabled while writing.

## 2. Archive metadata

```sql
CREATE TABLE vera_metadata (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

Required keys:

- `format_name`: `VERA`
- `format_version`: `0.2`
- `created_at`: ISO-8601 timestamp
- `created_by`: writer identity
- `creator_library`: writer library and version
- `default_embedding_model`: model used when embedding text and queries
- `default_embedding_dimension`: decimal vector dimension
- `archive_metadata`: a JSON object controlled by the caller

Source names, hashes, parser settings, OCR diagnostics, page counts, and
viewer configuration belong in `archive_metadata`; the storage engine does
not interpret them.

## 3. Required tables

```sql
CREATE TABLE chunks (
    chunk_id      TEXT PRIMARY KEY,
    text          TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE embeddings (
    chunk_id        TEXT PRIMARY KEY
                    REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    model_name      TEXT NOT NULL,
    model_dimension INTEGER NOT NULL,
    vector          BLOB NOT NULL,
    vector_format   TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE TABLE attachments (
    attachment_id TEXT PRIMARY KEY,
    mime_type     TEXT NOT NULL,
    filename      TEXT,
    data          BLOB NOT NULL,
    hash          TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL
);

CREATE TABLE chunk_attachments (
    chunk_id      TEXT NOT NULL
                  REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    attachment_id TEXT NOT NULL
                  REFERENCES attachments(attachment_id) ON DELETE RESTRICT,
    role           TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (chunk_id, attachment_id, role)
);

CREATE VIRTUAL TABLE chunks_fts USING fts5(
    chunk_id UNINDEXED,
    text
);
```

Integrity requirements:

1. Chunk IDs and attachment IDs MUST be non-empty and unique.
2. Chunk text MUST be non-empty.
3. `metadata_json` and `archive_metadata` MUST contain JSON objects.
4. Exactly one embedding and one FTS row MUST exist for every chunk.
5. Embedding byte length MUST equal `4 × model_dimension`.
6. `vector_format` MUST be `float32_le`.
7. Attachment `hash` MUST be the lowercase SHA-256 digest of `data`.
8. Every attachment reference MUST resolve.
9. Empty databases are valid.

## 4. Chunk records

A chunk is the only searchable record. Writers MUST submit final chunk text;
the database MUST NOT parse or split it. `metadata_json` may contain any
JSON-compatible application data, including:

```json
{
  "source_filename": "manual.pdf",
  "page_start": 12,
  "page_end": 12,
  "heading_path": "Chapter 4 > Detention",
  "regions": [
    {
      "page_number": 12,
      "bbox": [72.0, 144.0, 510.0, 220.0],
      "page_width": 612.0,
      "page_height": 792.0
    }
  ]
}
```

These keys are conventional, not required. Readers MUST preserve unknown
metadata.

## 5. Attachments

Attachments are optional opaque payloads. The storage engine stores,
retrieves, validates, and links them but MUST NOT parse, OCR, embed, chunk, or
search them. Applications may store original files, images, or structured
viewer payloads. `role` and attachment metadata are application-defined.

An attachment referenced by a chunk MUST NOT be deleted until its references
are removed. Unreferenced attachments MAY be deleted.

## 6. Embeddings

- Vectors are little-endian IEEE-754 float32 arrays.
- One database uses one configured embedding dimension.
- Callers MAY supply vectors. Otherwise the writer MAY invoke its configured
  embedding function.
- Queries MUST use a compatible model and dimension.
- `vera-hashing-384` retains the normative algorithm defined by the
  [0.1 specification](vera-spec-v0.1.md#62-the-vera-hashing-384-embedder-normative).

## 7. Mutations and transactions

Writers MUST make batch `add`, `upsert`, and `delete` operations transactional.
On failure, chunk rows, embeddings, FTS rows, and attachment links MUST roll
back together.

- `add` MUST fail when an ID already exists.
- `upsert` MUST insert or replace the record, embedding, FTS row, and links.
- Deleting a chunk MUST cascade to its embedding and links and MUST remove its
  FTS row in the same transaction.
- Read-only opens MUST reject mutations.

VERA uses SQLite's concurrency model: multiple readers are allowed; write
serialization and busy handling are implementation concerns.

## 8. Search semantics

Reference behavior:

- **keyword:** FTS5 `MATCH` ranked with `bm25()`, with OR-prefix fallback for
  ordinary text that does not match as a complete expression.
- **semantic:** cosine similarity against stored vectors.
- **hybrid:** min-max normalize semantic and keyword scores independently,
  then combine them with equal weight.
- **metadata filters:** exact top-level equality is the portable minimum.

Results MUST include the chunk ID, text, score, and metadata. Implementations
MAY include component scores.

## 9. Libraries

A `.vera-index/` is a rebuildable derived index over multiple `.vera` files.
It is not part of an individual archive and MUST NOT be treated as the source
of truth. Library indexes may be discarded and rebuilt from their archives.

## 10. Version compatibility

VERA 0.2 is a deliberate breaking change from the document-shaped 0.1
schema. A 0.2 writer MUST NOT label a file as 0.1. Implementations MAY provide
read-only 0.1 compatibility, but new writes use 0.2.

Because VERA remains pre-1.0, additional breaking changes may occur before the
format stabilizes.
