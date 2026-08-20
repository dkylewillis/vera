# Library index structure

A VERA library keeps each document in its own portable `.vera` archive. The
optional `.vera-index` directory is a disposable acceleration layer: it
duplicates enough metadata, keyword text, and vectors to search the library
efficiently, but the archives remain the source of truth.

## On-disk layout

```mermaid
flowchart TD
    libraryRoot["Library root"]
    archives["Nested .vera archives"]
    indexDir[".vera-index"]
    currentPointer["current.json"]
    buildLock["build.lock"]
    generations["generations"]
    activeGeneration["generation-active-id"]
    sqliteDb["index.sqlite3"]
    vectorFiles["vectors-model-hash-dimension.npy"]

    libraryRoot --> archives
    libraryRoot --> indexDir
    indexDir --> currentPointer
    indexDir --> buildLock
    indexDir --> generations
    currentPointer -->|"atomically points to"| activeGeneration
    generations --> activeGeneration
    activeGeneration --> sqliteDb
    activeGeneration --> vectorFiles
```

`current.json` identifies the active generation. A build writes and validates a
new generation before atomically replacing that pointer under `build.lock`.
After the swap, VERA deletes every other generation directory. Concurrent
readers that already opened the previous generation can finish the pointer
swap; leftover files are best-effort cleanup, not a retained history.

## Active generation contents

```mermaid
erDiagram
    index_metadata {
        TEXT key PK
        TEXT value
    }

    files {
        INTEGER file_id PK
        TEXT relative_path UK
        INTEGER size
        INTEGER mtime_ns
        TEXT content_hash
        TEXT source_hash
        TEXT source_filename
        TEXT title
        TEXT created_at
        TEXT metadata_json
    }

    skipped_files {
        TEXT relative_path PK
        INTEGER size
        INTEGER mtime_ns
        TEXT category
        TEXT reason
    }

    chunks {
        INTEGER row_id PK
        INTEGER file_id FK
        TEXT chunk_id
        TEXT document_id
        TEXT model_name
        INTEGER dimension
        INTEGER vector_row
        TEXT text
        INTEGER page_start
        INTEGER page_end
        TEXT heading_path
        TEXT source_filename
    }

    chunks_fts {
        INTEGER row_id
        TEXT text
        TEXT heading_path
        TEXT source_filename
    }

    vector_groups {
        TEXT model_name PK
        INTEGER dimension PK
        TEXT filename
        INTEGER row_count
    }

    files ||--o{ chunks : contains
    chunks ||--|| chunks_fts : "shares row_id"
    vector_groups ||--o{ chunks : "maps vector_row"
```

The relationships from `chunks` to `chunks_fts` and `vector_groups` are logical
rather than SQLite foreign keys:

- `chunks_fts.row_id` connects a keyword hit to its chunk.
- `(model_name, dimension)` selects a vector-group manifest.
- `chunks.vector_row` selects that chunk's row in the group's NumPy matrix.
- `chunks.file_id` resolves the hit to a root-relative `.vera` path in `files`.

## Indexed search path

```mermaid
flowchart LR
    query["Search query"]
    statusCheck{"Index fresh?"}
    keywordSearch["FTS5 keyword search"]
    queryEmbedding["Embed query per model"]
    vectorSearch["NumPy matrix search"]
    rankFusion["Normalize and rank-fuse hits"]
    chunkLookup["Resolve chunk and file references"]
    sourceArchive["Open source .vera archive"]
    citedResults["Text, pages, headings, figures, and regions"]
    directSearch["Direct archive fan-out search"]

    query --> statusCheck
    statusCheck -->|Yes| keywordSearch
    statusCheck -->|Yes| queryEmbedding
    queryEmbedding --> vectorSearch
    keywordSearch --> rankFusion
    vectorSearch --> rankFusion
    rankFusion --> chunkLookup
    chunkLookup --> sourceArchive
    sourceArchive --> citedResults
    statusCheck -->|"No: missing or stale"| directSearch
    directSearch --> citedResults
```

The index accelerates candidate retrieval. Complete source text, citation
geometry, figures, and the original document continue to come from the selected
`.vera` archives. See [VERA collection indexes](collection-index.md) for build,
update, freshness, fallback, and performance behavior.
