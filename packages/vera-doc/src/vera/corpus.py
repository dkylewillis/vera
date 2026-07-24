"""Corpus search: query a folder of .vera files as a single collection."""

from __future__ import annotations

import os
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .collection import VeraCollectionIndex, discover_vera_files, library_index_status
from .core.search import (
    context_chunks_for,
    fuse_hybrid_results,
    keyword_search,
    row_to_result,
    semantic_scores,
)
from .document import SearchResult, VeraDocument

_RRF_K = 60.0


@dataclass
class CorpusSearchResult(SearchResult):
    """A search result attributed to the .vera file it came from."""

    file: str = ""


def _with_file(result: SearchResult, file: str) -> CorpusSearchResult:
    return CorpusSearchResult(file=file, **result.as_dict())


class VeraCorpus:
    """A folder of .vera files searchable as one corpus.

    Documents needed for citations and figures are opened lazily with a
    bounded LRU cache. File fan-out search uses parallel short-lived
    connections; a fresh local collection index is preferred automatically.
    Each file's query embedding uses that file's recorded embedding model,
    so a corpus may mix models.

    Ranking: semantic results are merged by raw cosine score (comparable
    across files that share a model). Keyword and hybrid scores are only
    normalized within a file. Keyword and hybrid candidates use their
    within-file score with reciprocal rank as a tiebreaker; each result keeps
    its original score.
    """

    def __init__(
        self,
        directory: str,
        paths: list[str],
        *,
        recursive: bool = False,
        excludes: tuple[str, ...] = (),
        max_open_documents: int = 16,
        collection_index: VeraCollectionIndex | None = None,
        index_status: dict[str, Any] | None = None,
    ):
        self.directory = directory
        self.paths = paths
        self.recursive = recursive
        self.excludes = excludes
        self.max_open_documents = max(1, max_open_documents)
        self._docs: OrderedDict[str, VeraDocument] = OrderedDict()
        self._collection_index = collection_index
        self.index_status = index_status or {"exists": False, "fresh": False, "reasons": ["index is missing"]}

    @classmethod
    def open(
        cls,
        directory: str,
        *,
        recursive: bool | None = None,
        excludes: list[str] | tuple[str, ...] | None = None,
        max_open_documents: int = 16,
        use_index: bool = True,
    ) -> "VeraCorpus":
        root = Path(directory).resolve()
        if not root.is_dir():
            raise NotADirectoryError(directory)
        status = library_index_status(str(root), verify_hashes=False)
        effective_recursive = bool(status.get("recursive", False)) if recursive is None else recursive
        effective_excludes = (
            tuple(status.get("excludes", ()))
            if excludes is None and status.get("exists")
            else tuple(excludes or ())
        )
        paths = [
            str(path)
            for path in discover_vera_files(
                root,
                recursive=effective_recursive,
                excludes=effective_excludes,
            )
        ]
        if not paths:
            raise FileNotFoundError(f"No .vera files found in {directory}")
        config_matches = (
            effective_recursive == bool(status.get("recursive", False))
            and effective_excludes == tuple(status.get("excludes", ()))
        )
        collection_index = None
        if use_index and status.get("fresh") and config_matches:
            collection_index = VeraCollectionIndex.open(str(root), check_status=False)
        return cls(
            str(root),
            paths,
            recursive=effective_recursive,
            excludes=effective_excludes,
            max_open_documents=max_open_documents,
            collection_index=collection_index,
            index_status=status,
        )

    @classmethod
    def from_paths(cls, paths: list[str]) -> "VeraCorpus":
        """Build a corpus from an explicit list of .vera file paths."""
        resolved = [str(Path(p)) for p in paths]
        if not resolved:
            raise FileNotFoundError("No .vera files selected")
        if len(resolved) == 1:
            root = str(Path(resolved[0]).parent)
        else:
            try:
                root = os.path.commonpath(resolved)
            except ValueError:
                root = str(Path(resolved[0]).parent)
        return cls(root, sorted(resolved))

    def document(self, file: str) -> VeraDocument:
        """Return the (cached) open VeraDocument for a file in this corpus."""
        if file in self._docs:
            doc = self._docs.pop(file)
            self._docs[file] = doc
            return doc
        doc = VeraDocument.open(file)
        self._docs[file] = doc
        while len(self._docs) > self.max_open_documents:
            _, evicted = self._docs.popitem(last=False)
            evicted.close()
        return doc

    def close(self) -> None:
        for doc in self._docs.values():
            doc.close()
        self._docs.clear()
        if self._collection_index is not None:
            self._collection_index.close()
            self._collection_index = None

    def __enter__(self) -> "VeraCorpus":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @property
    def uses_index(self) -> bool:
        """Whether searches are currently served by the local collection index."""
        return self._collection_index is not None

    def inspect(self) -> dict[str, Any]:
        """Summarize the corpus: file count, total pages/chunks, models used."""
        files = []
        total_pages = 0
        total_chunks = 0
        models = set()
        for path in self.paths:
            info = self.document(path).inspect()
            files.append(
                {
                    "file": path,
                    "source": info.get("source"),
                    "pages": info.get("pages"),
                    "chunks": info.get("chunks"),
                    "embedding_model": info.get("default_embedding_model"),
                }
            )
            total_pages += info.get("pages") or 0
            total_chunks += info.get("chunks") or 0
            models.add(info.get("default_embedding_model"))
        return {
            "directory": self.directory,
            "file_count": len(self.paths),
            "pages": total_pages,
            "chunks": total_chunks,
            "embedding_models": sorted(m for m in models if m),
            "files": files,
            "recursive": self.recursive,
            "index": self.index_status,
        }

    def search(
        self,
        query: str,
        mode: str = "hybrid",
        top_k: int = 10,
        context_chunks: int = 0,
    ) -> list[CorpusSearchResult]:
        """Search every file in the corpus and return the fused top_k results."""
        mode = mode.lower()
        if mode not in {"semantic", "keyword", "hybrid"}:
            raise ValueError("mode must be semantic, keyword, or hybrid")
        if top_k < 0:
            raise ValueError("top_k must be non-negative")
        if context_chunks < 0:
            raise ValueError("context_chunks must be non-negative")
        if top_k == 0:
            return []
        if self._collection_index is not None:
            final = self._search_index(query, mode, top_k)
        else:
            per_file, models = self._search_files(query, mode, top_k)
            if mode == "semantic":
                final = self._fuse_semantic(per_file, models, top_k)
            else:
                final = self._fuse_rrf(per_file, top_k)
        if context_chunks:
            for result in final:
                doc = self.document(result.file)
                before, after = context_chunks_for(doc.conn, result.chunk_id, context_chunks)
                result.before_chunks = before
                result.after_chunks = after
        return final

    def _search_files(
        self,
        query: str,
        mode: str,
        top_k: int,
    ) -> tuple[dict[str, list[SearchResult]], dict[str, str]]:
        """Search files in parallel using short-lived, thread-local connections."""

        def search_path(
            path: str,
            *,
            allow_keyword_fallback: bool,
        ) -> tuple[str, list[SearchResult], str, bool]:
            doc = VeraDocument.open(path)
            try:
                row = doc.conn.execute(
                    "SELECT value FROM vera_metadata WHERE key = 'default_embedding_model'"
                ).fetchone()
                model = str(row["value"]) if row else ""
                if mode == "keyword":
                    results = keyword_search(
                        doc.conn,
                        query,
                        top_k,
                        allow_fallback=allow_keyword_fallback,
                    )
                    keyword_matched = bool(results)
                elif mode == "hybrid":
                    semantic = semantic_scores(doc.conn, query)
                    keyword = keyword_search(
                        doc.conn,
                        query,
                        max(top_k * 5, 50),
                        allow_fallback=allow_keyword_fallback,
                    )
                    results = fuse_hybrid_results(semantic, keyword, top_k)
                    keyword_matched = bool(keyword)
                else:
                    results = doc.search(query, mode=mode, top_k=top_k)
                    keyword_matched = False
                return path, results, model, keyword_matched
            finally:
                doc.close()

        def run(allow_keyword_fallback: bool) -> list[tuple[str, list[SearchResult], str, bool]]:
            if len(self.paths) == 1:
                return [search_path(self.paths[0], allow_keyword_fallback=allow_keyword_fallback)]
            workers = min(8, len(self.paths))
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="vera-corpus") as executor:
                return list(
                    executor.map(
                        lambda path: search_path(
                            path,
                            allow_keyword_fallback=allow_keyword_fallback,
                        ),
                        self.paths,
                    )
                )

        searched = run(allow_keyword_fallback=False)
        if mode in {"keyword", "hybrid"} and not any(matched for _, _, _, matched in searched):
            searched = run(allow_keyword_fallback=True)
        return (
            {path: results for path, results, _, _ in searched},
            {path: model for path, _, model, _ in searched},
        )

    @staticmethod
    def _fuse_semantic(
        per_file: dict[str, list[SearchResult]],
        models: dict[str, str],
        top_k: int,
    ) -> list[CorpusSearchResult]:
        model_groups: dict[str, list[tuple[str, SearchResult]]] = {}
        for path, results in per_file.items():
            model_groups.setdefault(models.get(path, ""), []).extend((path, result) for result in results)
        for results in model_groups.values():
            results.sort(key=lambda item: item[1].score, reverse=True)
        if len(model_groups) == 1:
            merged = next(iter(model_groups.values()))
            return [_with_file(result, path) for path, result in merged[:top_k]]
        fused = [
            (1.0 / (_RRF_K + rank), result.score, path, result)
            for results in model_groups.values()
            for rank, (path, result) in enumerate(results, start=1)
        ]
        fused.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [_with_file(result, path) for _, _, path, result in fused[:top_k]]

    def _search_index(self, query: str, mode: str, top_k: int) -> list[CorpusSearchResult]:
        assert self._collection_index is not None
        final: list[CorpusSearchResult] = []
        for hit in self._collection_index.search(query, mode=mode, top_k=top_k):
            path = str((Path(self.directory) / Path(hit.relative_path)).resolve())
            doc = self.document(path)
            row = doc.conn.execute(
                """
                SELECT c.*, d.source_filename
                FROM chunks c JOIN documents d ON d.document_id = c.document_id
                WHERE c.chunk_id = ?
                """,
                (hit.chunk_id,),
            ).fetchone()
            if row is None:
                continue
            result = row_to_result(row, hit.score)
            final.append(_with_file(result, path))
        return final

    @staticmethod
    def _fuse_rrf(per_file: dict[str, list[SearchResult]], top_k: int) -> list[CorpusSearchResult]:
        fused: list[tuple[float, float, str, SearchResult]] = []
        for path, results in per_file.items():
            for rank, result in enumerate(results, start=1):
                fused.append((result.score, 1.0 / (_RRF_K + rank), path, result))
        fused.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [_with_file(result, path) for _, _, path, result in fused[:top_k]]

    def regions_for(self, result: CorpusSearchResult) -> list[dict[str, Any]]:
        """Return highlight regions for a corpus result (see VeraDocument.get_chunk_regions)."""
        return self.document(result.file).regions_for(result)

    def figures_for(self, result: CorpusSearchResult, include_data: bool = False) -> list[dict[str, Any]]:
        """Return figures on the pages of a corpus result."""
        return self.document(result.file).figures_for(result, include_data=include_data)
