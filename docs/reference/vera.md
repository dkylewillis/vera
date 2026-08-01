# vera package

The `vera` package (`vera-doc` on PyPI) provides storage, search, corpus
queries, and library indexes for `.vera` archives.

::: vera
    options:
      members:
        - VeraDatabase
        - VeraDocument
        - VeraCorpus
        - VeraCollectionIndex
        - ChunkRecord
        - AttachmentRecord
        - AttachmentRef
        - QueryResult
        - SearchResult
        - CorpusSearchResult
        - SourceDocument
        - EmbeddingFunction
        - build_library_index
        - update_library_index
        - library_index_status
        - DuplicateRecordError
        - RecordNotFoundError
        - ReadOnlyError
      heading_level: 2
      show_if_no_docstring: true

See also the focused reference pages:

- [VeraDatabase](vera-database.md)
- [Records](vera-models.md)
- [VeraDocument](vera-document.md)
- [VeraCorpus](vera-corpus.md)
- [Library index](vera-collection.md)
