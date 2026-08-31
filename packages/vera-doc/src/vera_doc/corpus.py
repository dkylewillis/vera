"""Corpus search: query a folder of .vera files as a single collection."""

from __future__ import annotations

import os
from collections import OrderedDict
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from ._util import _MAX_TOP_K
from ._where import CHUNK_METADATA_FILTER_REASON, metadata_matches
from .collection import (
    VeraCollectionIndex,
    discover_vera_files,
    library_index_status,
)
from .document import VeraDocument
from .models import QueryResult
from .ranking import RRF_K, reciprocal_rank_fusion


@dataclass(frozen=True)
class CorpusSearchResult(QueryResult):
    """A search result attributed to the .vera file it came from."""

    file: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"file": self.file, **super().as_dict()}


def _archive_where_skips(doc: VeraDocument, where: Mapping[str, Any] | None) -> bool:
    """Skip a file when archive-level ``where`` keys fail the predicate."""
    if not where:
        return False
    combined = {**doc.format_metadata(), **dict(doc.metadata)}
    applicable = {key: value for key, value in where.items() if key in combined}
    return bool(applicable) and not metadata_matches(combined, applicable)


def _with_file(result: QueryResult, file: str) -> CorpusSearchResult:
    return CorpusSearchResult(
        record=result.record,
        score=result.score,
        semantic_score=result.semantic_score,
        keyword_score=result.keyword_score,
        before=result.before,
        after=result.after,
        file=file,
    )


def _corpus_root_for_paths(paths: list[str]) -> str:
    """Return a directory to attribute selected files, even across drives."""
    if len(paths) == 1:
        return str(Path(paths[0]).parent)
    try:
        return os.path.commonpath(paths)
    except ValueError:
        return str(Path(paths[0]).parent)


def _relative_to_corpus_root(path: str, directory: str) -> str:
    """Return a stable relative key, falling back to an absolute posix path.

    ``Path.relative_to`` raises ``ValueError`` when ``path`` is on another
    drive (Windows multi-select) or otherwise outside ``directory``. Hybrid
    fusion only needs a unique file key; search results still use ``path``.
    """
    resolved = Path(path).resolve()
    root = Path(directory).resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return resolved.as_posix()


def _hydrate_context_chunks(
    doc: VeraDocument,
    results: list[CorpusSearchResult],
    context_chunks: int,
) -> list[CorpusSearchResult]:
    """Attach ±N neighbors to hits without loading the full chunk table.

    Mirrors :meth:`VeraDocument.search`: ordered chunk ids, then ``get()`` only
    the ranked hits and their adjacent windows. Directory/index search used to
    call ``doc.get()`` (every row) per hit file when ``context_chunks > 0``.
    """
    if not context_chunks or not results:
        return results
    hit_ids = [result.record.id for result in results]
    ordered_ids = doc._chunk_ids_in_order()
    positions = {chunk_id: index for index, chunk_id in enumerate(ordered_ids)}
    extra: list[str] = []
    for record_id in hit_ids:
        position = positions.get(record_id)
        if position is None:
            continue
        extra.extend(ordered_ids[max(0, position - context_chunks) : position])
        extra.extend(ordered_ids[position + 1 : position + context_chunks + 1])
    needed = list(dict.fromkeys([*hit_ids, *extra]))
    by_id = {record.id: record for record in doc.get(needed)}
    hydrated: list[CorpusSearchResult] = []
    for result in results:
        position = positions.get(result.record.id)
        if position is None:
            hydrated.append(result)
            continue
        hydrated.append(
            replace(
                result,
                before=tuple(
                    by_id[chunk_id]
                    for chunk_id in ordered_ids[max(0, position - context_chunks) : position]
                    if chunk_id in by_id
                ),
                after=tuple(
                    by_id[chunk_id]
                    for chunk_id in ordered_ids[position + 1 : position + context_chunks + 1]
                    if chunk_id in by_id
                ),
            )
        )
    return hydrated


class VeraCorpus:
    """A folder of .vera files searchable as one corpus.

    Documents needed for citations and figures are opened lazily with a
    bounded LRU cache. File fan-out search uses parallel short-lived
    connections; a fresh local collection index is preferred automatically.
    Each file's query embedding uses that file's recorded embedding model,
    so a corpus may mix models.

    Ranking: semantic results are merged by raw cosine score (comparable
    across files that share a model). Mixed-model semantic lists and hybrid
    semantic+keyword lists use :func:`~vera_doc.ranking.reciprocal_rank_fusion`
    so a library searched with or without a local index returns the same
    chunk order for a fixed hybrid query. Keyword-only scores are only
    comparable within a file; those candidates keep their original score
    with reciprocal rank as a tiebreaker.
    """

    def __init__(
        self,
        directory: str,
        paths: list[str],
        *,
        recursive: bool = False,
        excludes: tuple[str, ...] = (),
        includes: tuple[str, ...] = (),
        max_open_documents: int = 16,
        collection_index: VeraCollectionIndex | None = None,
        index_status: dict[str, Any] | None = None,
        invalid_files: list[dict[str, str]] | None = None,
    ):
        self.directory = directory
        self.paths = paths
        self.recursive = recursive
        self.excludes = excludes
        self.includes = includes
        self.max_open_documents = max(1, max_open_documents)
        self._docs: OrderedDict[str, VeraDocument] = OrderedDict()
        self._collection_index = collection_index
        self._search_used_index: bool | None = None
        self.index_status = index_status or {
            "exists": False,
            "fresh": False,
            "reasons": ["index is missing"],
        }
        self.invalid_files = invalid_files or []
        self.skipped_semantic_model_groups: list[dict[str, Any]] = []

    @classmethod
    def open(
        cls,
        directory: str,
        *,
        recursive: bool | None = None,
        excludes: list[str] | tuple[str, ...] | None = None,
        includes: list[str] | tuple[str, ...] | None = None,
        max_open_documents: int = 16,
        use_index: bool = True,
        default_recursive: bool = False,
        allow_empty: bool = False,
    ) -> VeraCorpus:
        """Open a directory of ``.vera`` files for corpus search.

        Args:
            directory: Root directory containing ``.vera`` archives.
            recursive: When ``True``, include nested directories. When ``None``,
                use persisted index settings when an index exists.
            excludes: Glob patterns to skip.
            includes: Glob patterns that a relative path must match when
                provided. Omitted includes keep every discovered file.
            max_open_documents: LRU cache size for opened documents.
            use_index: When ``True``, use a fresh local index when available.
            default_recursive: Default recursion when no index exists.
            allow_empty: When ``True``, allow opening a directory with no
                valid archives.

        Returns:
            A corpus handle ready for :meth:`search`.

        Raises:
            NotADirectoryError: When ``directory`` is not a directory.
            FileNotFoundError: When no valid archives are found and
                ``allow_empty`` is false.
        """
        root = Path(directory).resolve()
        if not root.is_dir():
            raise NotADirectoryError(directory)
        status = library_index_status(str(root), verify_hashes=False)
        effective_recursive = (
            bool(status.get("recursive", default_recursive)) if recursive is None else recursive
        )
        effective_excludes = (
            tuple(status.get("excludes", ()))
            if excludes is None and status.get("exists")
            else tuple(excludes or ())
        )
        effective_includes = (
            tuple(status.get("includes", ()))
            if includes is None and status.get("exists")
            else tuple(includes or ())
        )
        config_matches = (
            effective_recursive == bool(status.get("recursive", False))
            and effective_excludes == tuple(status.get("excludes", ()))
            and effective_includes == tuple(status.get("includes", ()))
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
                    includes=effective_includes,
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
            includes=effective_includes,
            max_open_documents=max_open_documents,
            collection_index=collection_index,
            index_status=status,
            invalid_files=invalid_files,
        )

    @classmethod
    def from_paths(cls, paths: list[str]) -> VeraCorpus:
        """Build a corpus from an explicit list of .vera file paths.

        Selected files do not need a shared parent. Desktop multi-select can
        include paths on different Windows drives, where ``os.path.commonpath``
        raises ``ValueError``; the corpus root then falls back to the first
        file's parent. Result ``file`` attributes remain the original paths.
        """
        resolved = [str(Path(p)) for p in paths]
        if not resolved:
            raise FileNotFoundError("No .vera files selected")
        return cls(_corpus_root_for_paths(resolved), sorted(resolved))

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

    def __enter__(self) -> VeraCorpus:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @property
    def uses_index(self) -> bool:
        """Whether the most recent search used the local collection index.

        Before the first search, this is whether an index is attached.
        """
        if self._search_used_index is not None:
            return self._search_used_index
        return self._collection_index is not None

    def index_search_report(self) -> dict[str, Any]:
        """Index status for the most recent search, including fallback reasons."""
        status = dict(self.index_status)
        if self._search_used_index is False and self._collection_index is not None:
            reasons = list(status.get("reasons") or [])
            if CHUNK_METADATA_FILTER_REASON not in reasons:
                reasons.append(CHUNK_METADATA_FILTER_REASON)
            status["reasons"] = reasons
        return {"used": self.uses_index, **status}

    def inspect(
        self,
        *,
        progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Summarize the corpus and optionally report per-archive progress."""
        files = []
        total_pages = 0
        total_chunks = 0
        models = set()
        processed = 0
        if progress:
            progress(
                {
                    "phase": "inspecting",
                    "completed": 0,
                    "total": len(self.paths),
                    "input": "",
                    "chunks": 0,
                    "skipped": len(self.invalid_files),
                }
            )
        for path in self.paths:
            try:
                if progress:
                    progress(
                        {
                            "phase": "inspecting",
                            "completed": processed,
                            "total": len(self.paths),
                            "input": path,
                            "chunks": total_chunks,
                            "skipped": len(self.invalid_files),
                        }
                    )
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
            finally:
                processed += 1
                if progress:
                    progress(
                        {
                            "phase": "inspecting",
                            "completed": processed,
                            "total": len(self.paths),
                            "input": path,
                            "chunks": total_chunks,
                            "skipped": len(self.invalid_files),
                        }
                    )
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
        text: str,
        *,
        mode: str = "hybrid",
        top_k: int = 10,
        context_chunks: int = 0,
        where: Mapping[str, Any] | None = None,
    ) -> list[CorpusSearchResult]:
        """Search every file in the corpus and return the fused top_k results.

        ``where`` filters stored archive and chunk metadata before ``top_k``.
        """
        mode = mode.lower()
        if mode not in {"semantic", "keyword", "hybrid"}:
            raise ValueError("mode must be semantic, keyword, or hybrid")
        if top_k < 0:
            raise ValueError("top_k must be non-negative")
        if top_k > _MAX_TOP_K:
            raise ValueError(f"top_k must be at most {_MAX_TOP_K}")
        if context_chunks < 0:
            raise ValueError("context_chunks must be non-negative")
        if top_k == 0:
            self.skipped_semantic_model_groups = []
            self._search_used_index = False
            return []
        self.skipped_semantic_model_groups = []
        collection_index = self._collection_index
        if collection_index is not None and where and not collection_index.supports_where(where):
            collection_index = None
        use_index = collection_index is not None
        self._search_used_index = use_index
        if collection_index is not None:
            final = self._search_index(text, mode, top_k, where=where)
            self.skipped_semantic_model_groups = list(
                collection_index.skipped_semantic_model_groups
            )
        elif mode == "hybrid":
            candidate_limit = max(top_k * 5, 50)
            semantic_files, keyword_files, models = self._search_files_hybrid(
                text, candidate_limit, where=where
            )
            final = self._fuse_hybrid(semantic_files, keyword_files, models, top_k)
        else:
            per_file, models = self._search_files(text, mode, top_k, where=where)
            if mode == "semantic":
                final = self._fuse_semantic(per_file, models, top_k)
            else:
                final = self._fuse_rrf(per_file, top_k)
        if context_chunks:
            by_file: dict[str, list[int]] = {}
            for result_index, result in enumerate(final):
                by_file.setdefault(result.file, []).append(result_index)
            for path, indexes in by_file.items():
                replacements = _hydrate_context_chunks(
                    self.document(path),
                    [final[index] for index in indexes],
                    context_chunks,
                )
                for result_index, replacement in zip(indexes, replacements, strict=True):
                    final[result_index] = replacement
        return final

    def _search_files(
        self,
        query: str,
        mode: str,
        top_k: int,
        *,
        where: Mapping[str, Any] | None = None,
    ) -> tuple[dict[str, list[QueryResult]], dict[str, str]]:
        """Search files in parallel using short-lived, thread-local connections."""

        def search_path(
            path: str,
        ) -> tuple[str, list[QueryResult], str, str | None]:
            try:
                doc = VeraDocument.open(path)
                validation = doc.validate()
                if not validation["ok"]:
                    return path, [], "", "; ".join(validation["issues"])
                if _archive_where_skips(doc, where):
                    return path, [], "", None
                model = str(doc.inspect().get("embedding_model") or "")
                results = doc.search(
                    text=query,
                    mode=mode,  # type: ignore[arg-type]
                    top_k=top_k,
                    where=where,
                )
                return path, results, model, None
            except Exception as exc:
                return path, [], "", str(exc)
            finally:
                if "doc" in locals():
                    doc.close()

        def run() -> list[tuple[str, list[QueryResult], str, str | None]]:
            paths = [path for path in self.paths if not self._is_invalid(path)]
            if not paths:
                return []
            if len(paths) == 1:
                return [search_path(paths[0])]
            workers = min(8, len(paths))
            with ThreadPoolExecutor(
                max_workers=workers, thread_name_prefix="vera-corpus"
            ) as executor:
                return list(
                    executor.map(
                        search_path,
                        paths,
                    )
                )

        searched = run()
        for path, _, _, error in searched:
            if error:
                self._record_invalid(path, error)
        return (
            {path: results for path, results, _, error in searched if not error},
            {path: model for path, _, model, error in searched if not error},
        )

    def _search_files_hybrid(
        self,
        query: str,
        top_k: int,
        *,
        where: Mapping[str, Any] | None = None,
    ) -> tuple[dict[str, list[QueryResult]], dict[str, list[QueryResult]], dict[str, str]]:
        """Search each file once for semantic and keyword hits."""

        def search_path(
            path: str,
        ) -> tuple[str, list[QueryResult], list[QueryResult], str, str | None]:
            try:
                doc = VeraDocument.open(path)
                validation = doc.validate()
                if not validation["ok"]:
                    return path, [], [], "", "; ".join(validation["issues"])
                if _archive_where_skips(doc, where):
                    return path, [], [], "", None
                model = str(doc.inspect().get("embedding_model") or "")
                semantic = doc.search(text=query, mode="semantic", top_k=top_k, where=where)
                keyword = doc.search(text=query, mode="keyword", top_k=top_k, where=where)
                return path, semantic, keyword, model, None
            except Exception as exc:
                return path, [], [], "", str(exc)
            finally:
                if "doc" in locals():
                    doc.close()

        paths = [path for path in self.paths if not self._is_invalid(path)]
        if not paths:
            searched: list[tuple[str, list[QueryResult], list[QueryResult], str, str | None]] = []
        elif len(paths) == 1:
            searched = [search_path(paths[0])]
        else:
            workers = min(8, len(paths))
            with ThreadPoolExecutor(
                max_workers=workers, thread_name_prefix="vera-corpus"
            ) as executor:
                searched = list(executor.map(search_path, paths))
        for path, _, _, _, error in searched:
            if error:
                self._record_invalid(path, error)
        return (
            {path: semantic for path, semantic, _, _, error in searched if not error},
            {path: keyword for path, _, keyword, _, error in searched if not error},
            {path: model for path, _, _, model, error in searched if not error},
        )

    @staticmethod
    def _fuse_semantic(
        per_file: dict[str, list[QueryResult]],
        models: dict[str, str],
        top_k: int,
    ) -> list[CorpusSearchResult]:
        model_groups: dict[str, list[tuple[str, QueryResult]]] = {}
        for path, results in per_file.items():
            model_groups.setdefault(models.get(path, ""), []).extend(
                (path, result) for result in results
            )
        for grouped in model_groups.values():
            grouped.sort(key=lambda item: (-item[1].score, item[0], item[1].chunk_id))
        if len(model_groups) == 1:
            merged = next(iter(model_groups.values()))
            return [_with_file(result, path) for path, result in merged[:top_k]]
        lookup = {
            (path, result.chunk_id): (path, result)
            for results in model_groups.values()
            for path, result in results
        }
        fused = reciprocal_rank_fusion(
            [
                [(path, result.chunk_id) for path, result in results]
                for results in model_groups.values()
            ]
        )
        return [
            _with_file(lookup[key][1], lookup[key][0]) for key, _ in fused[:top_k] if key in lookup
        ]

    def _relative_corpus_path(self, path: str) -> str:
        return _relative_to_corpus_root(path, self.directory)

    def _fuse_hybrid(
        self,
        semantic_files: dict[str, list[QueryResult]],
        keyword_files: dict[str, list[QueryResult]],
        models: dict[str, str],
        top_k: int,
    ) -> list[CorpusSearchResult]:
        semantic_limit = max(sum(len(results) for results in semantic_files.values()), 1)
        semantic_ranked = [
            (self._relative_corpus_path(result.file), result.chunk_id)
            for result in self._fuse_semantic(semantic_files, models, semantic_limit)
        ]
        keyword_items = [
            (result.score, self._relative_corpus_path(path), result.chunk_id)
            for path, results in keyword_files.items()
            for result in results
        ]
        keyword_items.sort(key=lambda item: (-item[0], item[1], item[2]))
        keyword_ranked = [(relative, chunk_id) for _, relative, chunk_id in keyword_items]
        fused = reciprocal_rank_fusion([semantic_ranked, keyword_ranked])[:top_k]
        lookup: dict[tuple[str, str], tuple[str, QueryResult]] = {}
        semantic_lookup: dict[tuple[str, str], QueryResult] = {}
        keyword_lookup: dict[tuple[str, str], QueryResult] = {}
        for path, results in semantic_files.items():
            relative = self._relative_corpus_path(path)
            for result in results:
                key = (relative, result.chunk_id)
                semantic_lookup[key] = result
                lookup[key] = (path, result)
        for path, results in keyword_files.items():
            relative = self._relative_corpus_path(path)
            for result in results:
                key = (relative, result.chunk_id)
                keyword_lookup[key] = result
                lookup.setdefault(key, (path, result))
        return [
            _with_file(
                QueryResult(
                    record=lookup[key][1].record,
                    score=score,
                    semantic_score=(
                        semantic_lookup[key].semantic_score if key in semantic_lookup else None
                    ),
                    keyword_score=(
                        keyword_lookup[key].keyword_score if key in keyword_lookup else None
                    ),
                ),
                lookup[key][0],
            )
            for key, score in fused
            if key in lookup
        ]

    def _search_index(
        self,
        query: str,
        mode: str,
        top_k: int,
        *,
        where: Mapping[str, Any] | None = None,
    ) -> list[CorpusSearchResult]:
        assert self._collection_index is not None
        final: list[CorpusSearchResult] = []
        for hit in self._collection_index.search(query, mode=mode, top_k=top_k, where=where):
            path = str((Path(self.directory) / Path(hit.relative_path)).resolve())
            doc = self.document(path)
            records = doc.get([hit.chunk_id])
            if not records:
                continue
            final.append(
                _with_file(
                    QueryResult(record=records[0], score=hit.score),
                    path,
                )
            )
        return final

    @staticmethod
    def _fuse_rrf(per_file: dict[str, list[QueryResult]], top_k: int) -> list[CorpusSearchResult]:
        fused: list[tuple[float, float, str, QueryResult]] = []
        for path, results in per_file.items():
            for rank, result in enumerate(results, start=1):
                fused.append((result.score, 1.0 / (RRF_K + rank), path, result))
        fused.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [_with_file(result, path) for _, _, path, result in fused[:top_k]]
