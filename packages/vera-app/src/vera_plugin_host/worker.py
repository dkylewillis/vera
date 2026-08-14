"""JSON-lines ingest worker: discovery, convert, batch convert, cancel/skip."""

from __future__ import annotations

import json
import sys
import threading
import traceback
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from vera_ingest import batch_convert, convert
from vera_ingest.pipeline import (
    PLUGIN_API_VERSION,
    convert_options_from_mapping,
    list_ingest_pipeline_descriptors,
    list_ingest_pipeline_load_errors,
    list_ingest_pipelines,
)

from .cancellation import CancellationToken, CancelledError, SkipCurrentError

PROTOCOL_VERSION = 1
Request = dict[str, Any]
Response = dict[str, Any]
Handler = Callable[..., Any]


def _ingest_version() -> str:
    try:
        return version("vera-ingest")
    except PackageNotFoundError:
        return "unknown"


def handle_ping(_request: Request) -> dict[str, Any]:
    return {
        "status": "ok",
        "protocol": PROTOCOL_VERSION,
        "plugin_api": PLUGIN_API_VERSION,
        "python": sys.version.split()[0],
        "python_executable": sys.executable,
        "vera_ingest_version": _ingest_version(),
        "pipelines": list_ingest_pipelines(),
        "load_errors": list_ingest_pipeline_load_errors(),
    }


def handle_list_ingest_pipelines(_request: Request) -> dict[str, Any]:
    return {"pipelines": list_ingest_pipelines()}


def handle_describe_ingest_pipelines(_request: Request) -> dict[str, Any]:
    return {
        "pipelines": [item.as_dict() for item in list_ingest_pipeline_descriptors()],
        "load_errors": list_ingest_pipeline_load_errors(),
        "plugin_api": PLUGIN_API_VERSION,
        "vera_ingest_version": _ingest_version(),
    }


def _convert_kwargs(request: Request) -> dict[str, Any]:
    options = convert_options_from_mapping(request)
    parser = str(request.get("parser") or "pymupdf")
    options["parser"] = parser
    if "model" not in options:
        options["model"] = "hashing"
    if "chunk_size" in options:
        options["chunk_size"] = int(options["chunk_size"])
    if "overlap" in options:
        options["overlap"] = int(options["overlap"])
    if "ocr_dpi" in options:
        options["ocr_dpi"] = int(options["ocr_dpi"])
    if "store_original" in options:
        options["store_original"] = bool(options["store_original"])
    return options


def handle_convert(
    request: Request,
    write_event: Callable[[dict[str, Any]], None] | None = None,
    cancel: CancellationToken | None = None,
) -> dict[str, str]:
    input_path = str(request["input"])
    if write_event:
        write_event(
            {
                "event": "conversion_progress",
                "completed": 0,
                "total": 1,
                "input": input_path,
            }
        )
    output = convert(
        input_path,
        str(request["output"]),
        cancel=cancel,
        **_convert_kwargs(request),
    )
    if write_event:
        write_event(
            {
                "event": "conversion_progress",
                "completed": 1,
                "total": 1,
                "input": input_path,
            }
        )
    return {"output": output}


def handle_batch_convert(
    request: Request,
    write_event: Callable[[dict[str, Any]], None] | None = None,
    cancel: CancellationToken | None = None,
) -> dict[str, Any]:
    def report_progress(completed: int, total: int, input_path: str) -> None:
        if cancel:
            cancel.raise_if_interrupted()
        if write_event:
            write_event(
                {
                    "event": "conversion_progress",
                    "completed": completed,
                    "total": total,
                    "input": input_path,
                }
            )

    raw_paths = request.get("paths")
    paths: list[str] | None = None
    if isinstance(raw_paths, list):
        paths = [str(item) for item in raw_paths if str(item).strip()]
        if not paths:
            paths = None

    directory = request.get("directory")
    progress_label = (
        f"{len(paths)} selected PDF{'s' if len(paths) != 1 else ''}"
        if paths is not None
        else str(directory or "")
    )
    if write_event:
        write_event(
            {
                "event": "conversion_progress",
                "completed": 0,
                "total": 0,
                "input": progress_label,
                "phase": "discovering",
            }
        )
    if cancel:
        cancel.raise_if_interrupted()

    return batch_convert(
        None if paths is not None else str(directory),
        paths=paths,
        recursive=bool(request.get("recursive", True)),
        overwrite=bool(request.get("overwrite", False)),
        progress=report_progress,
        cancel=cancel,
        **_convert_kwargs(request),
    )


HANDLERS: dict[str, Handler] = {
    "ping": handle_ping,
    "list_ingest_pipelines": handle_list_ingest_pipelines,
    "describe_ingest_pipelines": handle_describe_ingest_pipelines,
    "convert": handle_convert,
    "batch_convert": handle_batch_convert,
}

_stdout_lock = threading.Lock()
_inflight_lock = threading.Lock()
_inflight_requests: dict[str, CancellationToken] = {}


def _write_response(response: Response) -> None:
    with _stdout_lock:
        print(json.dumps(response), flush=True)


def _cancelled_error_message(action: str, exc: BaseException | None = None) -> str:
    if exc and str(exc):
        return str(exc)
    if action in {"convert", "batch_convert"}:
        return "Conversion cancelled"
    return "Request cancelled"


def handle(request: Request, cancel: CancellationToken | None = None) -> Response:
    request_id = request.get("id")
    action = str(request.get("action", ""))
    try:
        if action not in HANDLERS:
            raise ValueError(f"Unknown action: {action}")
        if action in {"convert", "batch_convert"}:

            def _emit(data: dict[str, Any]) -> None:
                _write_response({**data, "id": request_id})

            result = HANDLERS[action](request, write_event=_emit, cancel=cancel)
        else:
            result = HANDLERS[action](request)
        return {"id": request_id, "ok": True, "result": result}
    except CancelledError as exc:
        return {
            "id": request_id,
            "ok": False,
            "error": _cancelled_error_message(action, exc),
            "cancelled": True,
        }
    except SkipCurrentError as exc:
        return {
            "id": request_id,
            "ok": False,
            "error": str(exc) or "File skipped",
            "cancelled": True,
        }
    except Exception as exc:
        if cancel and cancel.cancelled:
            return {
                "id": request_id,
                "ok": False,
                "error": _cancelled_error_message(action),
                "cancelled": True,
            }
        return {
            "id": request_id,
            "ok": False,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


def _run_cancellable_request(
    request: Request,
    request_id: str,
    cancel: CancellationToken,
) -> None:
    try:
        _write_response(handle(request, cancel=cancel))
    finally:
        with _inflight_lock:
            _inflight_requests.pop(request_id, None)


def main() -> int:
    """Read JSON-lines requests from stdin and write responses to stdout."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            response: Response = {"id": None, "ok": False, "error": str(exc)}
        else:
            action = str(request.get("action", ""))
            if action == "cancel":
                target_id = str(request.get("target_id") or "")
                with _inflight_lock:
                    cancel = _inflight_requests.get(target_id)
                if cancel:
                    cancel.cancel()
                response = {
                    "id": request.get("id"),
                    "ok": True,
                    "result": {"target_id": target_id, "cancelled": bool(cancel)},
                }
            elif action == "skip":
                target_id = str(request.get("target_id") or "")
                with _inflight_lock:
                    cancel = _inflight_requests.get(target_id)
                if cancel:
                    cancel.skip()
                response = {
                    "id": request.get("id"),
                    "ok": True,
                    "result": {"target_id": target_id, "skipped": bool(cancel)},
                }
            elif action in {"convert", "batch_convert"}:
                request_id = str(request.get("id") or "")
                if not request_id:
                    response = {
                        "id": None,
                        "ok": False,
                        "error": f"{action} requests require an id",
                    }
                else:
                    cancel = CancellationToken()
                    with _inflight_lock:
                        _inflight_requests[request_id] = cancel
                    threading.Thread(
                        target=_run_cancellable_request,
                        args=(request, request_id, cancel),
                        daemon=True,
                    ).start()
                    continue
            else:
                response = handle(request)
        _write_response(response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
