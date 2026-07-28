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
        invalid_files: list[dict[str, str]] | None = None,
    ):
        self.directory = directory
        self.paths = paths
        self.recursive = recursive
        self.excludes = excludes
        self.max_open_documents = max(1, max_open_documents)
        self._docs: OrderedDict[str, VeraDocument] = OrderedDict()
        self._collection_index = collection_index
        self.index_status = index_status or {"exists": False, "fresh": False, "reasons": ["index is missing"]}
        self.invalid_files = invalid_files or []
        self.skipped_semantic_model_groups: list[dict[str, Any]] = []

    @classmethod
    def open(
        cls,
        directory: str,
        *,
        recursive: bool | None = None,
        excludes: list[str] | tuple[str, ...] | None = None,
        max_open_documents: int = 16,
        use_index: bool = True,
        default_recursive: bool = False,
        allow_empty: bool = False,
    ) -> "VeraCorpus":
        root = Path(directory).resolve()
        if not root.is_dir():
            raise NotADirectoryError(directory)
        status = library_index_status(str(root), verify_hashes=False)
        effective_recursive = (
            bool(status.get("recursive", default_recursive))
            if recursive is None
            else recursive
        )
        effective_excludes = (
            tuple(status.get("excludes", ()))
            if excludes is None and status.get("exists")
            else tuple(excludes or ())
        )
        config_matches = (
            effective_recursive == bool(status.get("recursive", False))
            and effective_excludes == tuple(status.get("excludes", ()))
        )
        collection_index = None
        if use_index and status.get("fresh") and config_matches:
            collection_index = VeraCollectionIndex.open(str(root), check_status=False)
            paths = [
                str((root / relative_path).resolve())
                for relative_path in collection_index.document_paths()
            ]
        else:
            paths = [
                str(path)
                for path in discover_vera_files(
                    root,
                    recursive=effective_recursive,
                    excludes=effective_excludes,
                )
            ]
        if not paths and not allow_empty:
            if collection_index is not None:
                collection_index.close()
            raise FileNotFoundError(f"No .vera files found in {directory}")
        invalid_files = []
        if status.get("fresh"):
            invalid_files = [
                {
                    "file": str((root / entry["file"]).resolve()),
                    "category": str(entry.get("category", "invalid")),
                    "reason": str(entry["reason"]),
                }
                for entry in status.get("skipped_files", [])
            ]
        return cls(
            str(root),
            paths,
            recursive=effective_recursive,
            excludes=effective_excludes,
            max_open_documents=max_open_documents,
            collection_index=collection_index,
            index_status=status,
            invalid_files=invalid_files,
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
            if self._is_invalid(path):
                continue
            try:
                doc = self.document(path)
                validation = doc.validate()
                if not validation["ok"]:
                    self._record_invalid(path, "; ".join(validation["issues"]))
                    continue
                info = doc.inspect()
            except Exception as exc:
                self._record_invalid(path, str(exc))
                continue
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
            "file_count": len(files),
            "discovered_file_count": len(self.paths),
            "skipped": len(self.invalid_files),
            "skipped_files": list(self.invalid_files),
            "pages": total_pages,
            "chunks": total_chunks,
            "embedding_models": sorted(m for m in models if m),
            "files": files,
            "recursive": self.recursive,
            "index": self.index_status,
            "summary_source": "archives",
            "summary_complete": True,
        }

    def inspect_summary(self) -> dict[str, Any]:
        """Open a library quickly without validating every archive.

        A fresh collection index supplies persisted metrics from its last
        validated build. Missing or stale indexes return discovery counts only;
        callers can run ``inspect`` explicitly when they need a deep scan.
        """
        if self._collection_index is not None:
            summary = self._collection_index.inspect_summary()
            return {
                "directory": self.directory,
                **summary,
                "discovered_file_count": len(self.paths),
                "skipped": len(self.invalid_files),
                "skipped_files": list(self.invalid_files),
                "recursive": self.recursive,
                "index": self.index_status,
                "summary_source": "index",
                "summary_complete": True,
            }
        return {
            "directory": self.directory,
            "file_count": len(self.paths),
            "discovered_file_count": len(self.paths),
            "skipped": 0,
            "skipped_files": [],
            "pages": None,
            "chunks": None,
            "embedding_models": [],
            "files": [{"file": path} for path in self.paths],
            "recursive": self.recursive,
            "index": self.index_status,
            "summary_source": "discovery",
            "summary_complete": False,
        }

    def _is_invalid(self, path: str) -> bool:
        normalized = os.path.normcase(str(Path(path).resolve()))
        return any(
            os.path.normcase(str(Path(entry["file"]).resolve())) == normalized
            for entry in self.invalid_files
        )

    def _record_invalid(self, path: str, reason: str) -> None:
        if self._is_invalid(path):
            return
        self.invalid_files.append(
            {"file": str(Path(path).resolve()), "category": "invalid", "reason": reason}
        )

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
            self.skipped_semantic_model_groups = []
            return []
        self.skipped_semantic_model_groups = []
        if self._collection_index is not None:
            final = self._search_index(query, mode, top_k)
            self.skipped_semantic_model_groups = list(
                self._collection_index.skipped_semantic_model_groups
            )
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
        ) -> tuple[str, list[SearchResult], str, bool, str | None]:
            try:
                doc = VeraDocument.open(path)
                validation = doc.validate()
                if not validation["ok"]:
                    return path, [], "", False, "; ".join(validation["issues"])
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
                return path, results, model, keyword_matched, None
            except Exception as exc:
                return path, [], "", False, str(exc)
            finally:
                if "doc" in locals():
                    doc.close()

        def run(
            allow_keyword_fallback: bool,
        ) -> list[tuple[str, list[SearchResult], str, bool, str | None]]:
            paths = [path for path in self.paths if not self._is_invalid(path)]
            if not paths:
                return []
            if len(paths) == 1:
                return [search_path(paths[0], allow_keyword_fallback=allow_keyword_fallback)]
            workers = min(8, len(paths))
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="vera-corpus") as executor:
                return list(
                    executor.map(
                        lambda path: search_path(
                            path,
                            allow_keyword_fallback=allow_keyword_fallback,
                        ),
                        paths,
                    )
                )

        searched = run(allow_keyword_fallback=False)
        for path, _, _, _, error in searched:
            if error:
                self._record_invalid(path, error)
        if mode in {"keyword", "hybrid"} and not any(
            matched for _, _, _, matched, _ in searched
        ):
            searched = run(allow_keyword_fallback=True)
            for path, _, _, _, error in searched:
                if error:
                    self._record_invalid(path, error)
        return (
            {path: results for path, results, _, _, error in searched if not error},
            {path: model for path, _, model, _, error in searched if not error},
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
