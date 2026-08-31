"""Open VERA documents and corpora for sidecar handlers."""

from __future__ import annotations

from pathlib import Path

from vera_app.types import Request
from vera_doc import VeraDocument
from vera_doc.corpus import VeraCorpus


def open_document(path: str) -> VeraDocument:
    return VeraDocument.open(path)


def open_corpus(path: str, request: Request) -> VeraCorpus:
    recursive_value = request.get("recursive")
    recursive = None if recursive_value is None else bool(recursive_value)
    excludes_value = request.get("excludes")
    excludes = (
        [str(value) for value in excludes_value if str(value).strip()]
        if isinstance(excludes_value, list)
        else None
    )
    includes_value = request.get("includes")
    includes = (
        [str(value) for value in includes_value if str(value).strip()]
        if isinstance(includes_value, list)
        else None
    )
    return VeraCorpus.open(
        path,
        recursive=recursive,
        excludes=excludes,
        includes=includes,
        default_recursive=bool(request.get("default_recursive", False)),
        allow_empty=bool(request.get("allow_empty", False)),
    )


def resolve_target(request: Request):
    """Open the search/inspect target for a request.

    Returns a VeraCorpus when multiple paths are selected or the path is a
    directory; otherwise a single VeraDocument. Single-file selection keeps
    the original single-document code path.
    """
    paths = request.get("paths")
    if isinstance(paths, list):
        files = [str(p) for p in paths if str(p).strip()]
        if len(files) > 1:
            return VeraCorpus.from_paths(files)
        if len(files) == 1:
            return (
                open_corpus(files[0], request)
                if Path(files[0]).is_dir()
                else open_document(files[0])
            )
    path = str(request["path"])
    return open_corpus(path, request) if Path(path).is_dir() else open_document(path)


def scoped_single_file(request: Request) -> str | None:
    """Return the source path when a request is scoped to exactly one file.

    Single-document search results don't carry a `file` field (unlike corpus
    results), but the UI needs it to locate and highlight the source when the
    search was scoped via checkbox rather than an opened document. Returns the
    explicit single path, or the request `path` when it points at a file.
    """
    paths = request.get("paths")
    if isinstance(paths, list):
        files = [str(p) for p in paths if str(p).strip()]
        if len(files) == 1:
            return None if Path(files[0]).is_dir() else files[0]
        if len(files) > 1:
            return None
    path = str(request.get("path") or "")
    if path and not Path(path).is_dir():
        return path
    return None
