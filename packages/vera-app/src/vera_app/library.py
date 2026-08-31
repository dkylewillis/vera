"""Library index sidecar handlers."""

from __future__ import annotations

from typing import Any

from vera_app.types import Request, WriteEvent
from vera_doc import build_library_index, library_index_status, update_library_index


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
