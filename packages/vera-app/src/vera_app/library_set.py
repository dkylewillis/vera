"""Search several libraries together as one Search/Ask scope."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from vera_doc import VeraDocument
from vera_doc.corpus import CorpusSearchResult, VeraCorpus
from vera_doc.ranking import reciprocal_rank_fusion


def _file_key(path: str) -> str:
    return os.path.normcase(str(Path(path).resolve()))


class LibrarySet:
    """Several library corpora searched as one scope.

    Each library keeps its own collection index, recursion, and excludes.
    Per-library rankings are merged with reciprocal rank fusion, so every
    library contributes its best hits and raw scores from different indexes
    or embedding models are never compared directly.
    """

    def __init__(self, corpora: list[VeraCorpus]):
        if not corpora:
            raise FileNotFoundError("No libraries selected")
        self.corpora = corpora
        self.skipped_semantic_model_groups: list[dict[str, Any]] = []
        self._owners: dict[str, VeraCorpus] = {}
        self._loose_docs: dict[str, VeraDocument] = {}

    def search(
        self,
        text: str,
        *,
        mode: str = "hybrid",
        top_k: int = 10,
        context_chunks: int = 0,
        where: Mapping[str, Any] | None = None,
    ) -> list[CorpusSearchResult]:
        self.skipped_semantic_model_groups = []
        ranked: list[list[tuple[str, str]]] = []
        lookup: dict[tuple[str, str], CorpusSearchResult] = {}
        for corpus in self.corpora:
            results = corpus.search(
                text, mode=mode, top_k=top_k, context_chunks=context_chunks, where=where
            )
            self.skipped_semantic_model_groups.extend(corpus.skipped_semantic_model_groups)
            keys: list[tuple[str, str]] = []
            for result in results:
                key = (_file_key(result.file), result.chunk_id)
                if key in lookup:
                    continue
                lookup[key] = result
                self._owners[key[0]] = corpus
                keys.append(key)
            ranked.append(keys)
        if len(ranked) == 1:
            return [lookup[key] for key in ranked[0][:top_k]]
        fused = reciprocal_rank_fusion(ranked)[:top_k]
        return [replace(lookup[key], score=score) for key, score in fused]

    def document(self, file: str) -> VeraDocument:
        key = _file_key(file)
        owner = self._owners.get(key)
        if owner is not None:
            return owner.document(file)
        doc = self._loose_docs.get(key)
        if doc is None:
            doc = VeraDocument.open(file)
            self._loose_docs[key] = doc
        return doc

    def close(self) -> None:
        for corpus in self.corpora:
            corpus.close()
        for doc in self._loose_docs.values():
            doc.close()
        self._loose_docs.clear()
