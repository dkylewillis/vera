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
    set_folder_pipeline,
    sync_library,
)
from vera_ingest.library import (
    library_pipelines as _library_pipelines,
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


def library_init(
    request: Request, write_event: WriteEvent | None = None, cancel: Any | None = None
) -> dict[str, Any]:
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
        pipeline_rules=_rules(request.get("pipeline_rules")),
    )


def _rules(value: object) -> list[dict[str, Any]] | None:
    if not isinstance(value, list):
        return None
    return [dict(item) for item in value if isinstance(item, dict)]


def library_pipelines(request: Request) -> dict[str, Any]:
    return _library_pipelines(str(request["path"]))


def library_set_pipeline(request: Request) -> dict[str, Any]:
    """Set or clear one folder's pipeline. ``path`` is that folder.

    Without ``parser`` the folder's rule for ``source_format`` (default
    ``pdf``) is removed, so that format follows the parent folder again.
    """
    parser = request.get("parser")
    source_format = request.get("source_format")
    folder = request.get("folder") if "folder" in request else None
    return set_folder_pipeline(
        str(request["path"]),
        folder=str(folder) if isinstance(folder, str) else None,
        parser=str(parser) if parser else None,
        pipeline_options=_mapping(request.get("pipeline_options")),
        clear=not parser,
        source_format=str(source_format) if source_format else "pdf",
    )


def library_sync(
    request: Request, write_event: WriteEvent | None = None, cancel: Any | None = None
) -> dict[str, Any]:
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
