# vera_doc package

The `vera_doc` package (`vera-doc` on PyPI) provides storage, search, corpus
queries, and library indexes for `.vera` archives.

::: vera_doc
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
        - EmbedderOptions
        - EmbedderDescriptor
        - EmbeddingModelInfo
        - EmbedderPreflightResult
        - UnknownEmbeddingModelError
        - get_embedder
        - register_embedder
        - register_embedder_descriptor
        - register_embedder_models
        - describe_embedder
        - list_embedding_providers
        - list_embedding_provider_descriptors
        - list_embedding_models
        - preflight_embedder
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
