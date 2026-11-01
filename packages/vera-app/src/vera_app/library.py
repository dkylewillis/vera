"""Library index and managed-folder sidecar handlers."""

from __future__ import annotations

from typing import Any

from vera_app.types import Request, WriteEvent
from vera_doc import build_library_index, library_index_status, update_library_index
from vera_ingest.library import (
    init_library,
    library_status,
    list_trash,
    restore_from_trash,
    sync_library,
)


def index_status(request: Request) -> dict[str, Any]:
    return library_index_status(
        str(request["path"]),
        verify_hashes=bool(request.get("verify_hashes", True)),
    )


def index_build(request: Request, write_event: WriteEvent | None = None) -> dict[str, Any]:
    def report_progress(update: dict[str, Any]) -> None:
        if write_event:
            write_event({"event": "index_progress", **update})

    excludes = request.get("excludes")
    includes = request.get("includes")
    return build_library_index(
        str(request["path"]),
        recursive=bool(request.get("recursive", True)),
        excludes=[str(value) for value in excludes] if isinstance(excludes, list) else (),
        includes=[str(value) for value in includes] if isinstance(includes, list) else (),
        progress=report_progress,
    )


def index_update(request: Request, write_event: WriteEvent | None = None) -> dict[str, Any]:
    def report_progress(update: dict[str, Any]) -> None:
        if write_event:
            write_event({"event": "index_progress", **update})

    return update_library_index(str(request["path"]), progress=report_progress)


def _mapping(value: object) -> dict[str, Any] | None:
    return dict(value) if isinstance(value, dict) else None


def library_init(request: Request, write_event: WriteEvent | None = None, cancel: Any | None = None) -> dict[str, Any]:
    del write_event, cancel
    parser = request.get("parser")
    return init_library(
        str(request["path"]),
        adopt=bool(request.get("adopt", False)),
        model=str(request.get("model") or "hashing"),
        parser=str(parser) if parser else None,
        pipeline_options=_mapping(request.get("pipeline_options")),
        embedder_options=_mapping(request.get("embedder_options")),
        metadata=_mapping(request.get("metadata")),
    )


def library_sync(request: Request, write_event: WriteEvent | None = None, cancel: Any | None = None) -> dict[str, Any]:
    def report_progress(update: dict[str, Any]) -> None:
        if write_event:
            write_event({"event": "library_progress", **update})

    return sync_library(
        str(request["path"]),
        dry_run=bool(request.get("dry_run", False)),
        confirm_deletes=bool(request.get("confirm_deletes", False)),
        reconvert=bool(request.get("reconvert", False)),
        progress=report_progress,
        cancel=cancel,
        require=bool(request.get("require", False)),
    )


def library_info(request: Request) -> dict[str, Any]:
    return library_status(str(request["path"]))


def library_trash_list(request: Request) -> dict[str, Any]:
    return list_trash(str(request["path"]))


def library_restore(request: Request) -> dict[str, Any]:
    return restore_from_trash(str(request["path"]), str(request.get("entry") or ""))
