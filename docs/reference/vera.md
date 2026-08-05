# vera package

The `vera` package (`vera-doc` on PyPI) provides storage, search, corpus
queries, and library indexes for `.vera` archives.

::: vera
    options:
      members:
        - VeraDocument
        - VeraCorpus
        - VeraCollectionIndex
        - ChunkRecord
        - AttachmentRecord
        - AttachmentRef
        - QueryResult
        - CorpusSearchResult
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

- [VeraDocument](vera-document.md)
- [Records](vera-models.md)
- [VeraCorpus](vera-corpus.md)
- [Library index](vera-collection.md)
