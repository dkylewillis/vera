"""JSON-lines sidecar process: dispatch Electron requests to handler modules."""

from __future__ import annotations

import json
import os
import sys
import threading
import traceback
from typing import Any

from vera_ingest_pymupdf import (
    ensure_registered as ensure_pymupdf_pipeline_registered,
)

# PyInstaller freezes and PYTHONPATH-only app runs often omit entry-point
# metadata; the sidecar hard-depends on the default PDF pipeline.
ensure_pymupdf_pipeline_registered()

try:
    from vera_ingest_docling import (
        ensure_registered as ensure_docling_pipeline_registered,
    )
except ImportError:
    pass
else:
    ensure_docling_pipeline_registered()

from vera_app import convert as convert_handlers
from vera_app import library as library_handlers
from vera_app.cancellation import CancellationToken, CancelledError, SkipCurrentError
from vera_app.chat import answer as _answer
from vera_app.chat import list_llm_models as _list_models
from vera_app.chat import list_modes as _list_modes
from vera_app.inspect import inspect as _inspect
from vera_app.inspect import page as _page
from vera_app.inspect import validate as _validate
from vera_app.llm import ProviderHttpError
from vera_app.protocol import SIDECAR_ACTIONS
from vera_app.search import figure_data as _figure_data
from vera_app.search import search_report as _search_report
from vera_app.source import export as _export
from vera_app.source import source as _source
from vera_app.types import Handler, Request, Response

HANDLERS: dict[str, Handler] = {
    "ping": lambda request: {"status": "ok"},
    "inspect": _inspect,
    "validate": _validate,
    "index_status": library_handlers.index_status,
    "index_build": library_handlers.index_build,
    "index_update": library_handlers.index_update,
    "search": _search_report,
    "figure_data": _figure_data,
    "answer": _answer,
    "convert": convert_handlers.handle_convert,
    "batch_convert": convert_handlers.handle_batch_convert,
    "export": _export,
    "source": _source,
    "page": _page,
    "list_models": _list_models,
    "list_embedding_providers": convert_handlers.handle_list_embedding_providers,
    "describe_embedding_providers": convert_handlers.handle_describe_embedding_providers,
    "list_embedding_models": convert_handlers.handle_list_embedding_models,
    "preflight_embedder": convert_handlers.handle_preflight_embedder,
    "list_ingest_pipelines": convert_handlers.handle_list_ingest_pipelines,
    "describe_ingest_pipelines": convert_handlers.handle_describe_ingest_pipelines,
    "ocr_languages_list": convert_handlers.handle_ocr_languages_list,
    "ocr_languages_download": convert_handlers.handle_ocr_languages_download,
    "prepare_docling": convert_handlers.handle_prepare_docling,
    "list_modes": _list_modes,
}

_CONTROL_ACTIONS = {"cancel", "skip"}
if set(HANDLERS) | _CONTROL_ACTIONS != set(SIDECAR_ACTIONS):
    missing = set(SIDECAR_ACTIONS) - (set(HANDLERS) | _CONTROL_ACTIONS)
    extra = (set(HANDLERS) | _CONTROL_ACTIONS) - set(SIDECAR_ACTIONS)
    raise RuntimeError(f"sidecar action mismatch missing={sorted(missing)} extra={sorted(extra)}")

_stdout_lock = threading.Lock()
_inflight_lock = threading.Lock()
_inflight_requests: dict[str, CancellationToken] = {}


def _write_response(response: Response) -> None:
    with _stdout_lock:
        print(json.dumps(response), flush=True)


def _debug_sidecar() -> bool:
    """Return True when packaged IPC may include Python tracebacks."""
    value = os.environ.get("VERA_APP_DEBUG", "").strip().lower()
    return value not in {"", "0", "false", "no", "off"}


def _cancelled_error_message(action: str, exc: BaseException | None = None) -> str:
    if exc and str(exc):
        return str(exc)
    if action in {"convert", "batch_convert"}:
        return "Conversion cancelled"
    if action == "prepare_docling":
        return "Docling model download cancelled"
    if action == "ocr_languages_download":
        return "OCR language download cancelled"
    if action == "inspect":
        return "Inspection cancelled"
    if action == "source":
        return "Source loading cancelled"
    if action == "search":
        return "Search cancelled"
    return "Answer cancelled"


def handle(request: Request, cancel: CancellationToken | None = None) -> Response:
    """Dispatch a JSON-RPC request from the Electron renderer.

    Args:
        request: Parsed request dict with ``action`` and optional ``params``.
        cancel: Optional token checked by long-running handlers.

    Returns:
        Response dict with ``id``, ``ok``, and result or error fields.
    """
    request_id = request.get("id")
    action = str(request.get("action", ""))
    try:
        if action not in HANDLERS:
            raise ValueError(f"Unknown action: {action}")
        if action == "answer":

            def _emit(data: dict[str, Any]) -> None:
                _write_response({**data, "id": request_id})

            result = _answer(request, write_event=_emit, cancel=cancel)
        elif action in {"convert", "batch_convert", "ocr_languages_download", "prepare_docling"}:

            def _emit(data: dict[str, Any]) -> None:
                _write_response({**data, "id": request_id})

            result = HANDLERS[action](request, write_event=_emit, cancel=cancel)
        elif action == "inspect":

            def _emit(data: dict[str, Any]) -> None:
                _write_response({**data, "id": request_id})

            result = _inspect(request, write_event=_emit, cancel=cancel)
        elif action == "search":
            result = _search_report(request, cancel=cancel)
        elif action in {"index_build", "index_update"}:

            def _emit(data: dict[str, Any]) -> None:
                _write_response({**data, "id": request_id})

            result = HANDLERS[action](request, write_event=_emit)
        elif action == "source":
            result = _source(request, cancel=cancel)
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
        # Single-file convert has nothing to continue; treat skip like cancel.
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
                "error": _cancelled_error_message(
                    action, exc if isinstance(exc, CancelledError) else None
                ),
                "cancelled": True,
            }
        response: Response = {
            "id": request_id,
            "ok": False,
            "error": str(exc),
        }
        if _debug_sidecar():
            response["traceback"] = traceback.format_exc()
        if isinstance(exc, ProviderHttpError):
            response["provider_error_detail"] = exc.raw_detail
        return response


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


def _run_background_request(request: Request) -> None:
    _write_response(handle(request))


def main() -> int:
    """Read JSON-RPC requests from stdin and write responses to stdout."""
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
            elif action in {
                "answer",
                "convert",
                "batch_convert",
                "inspect",
                "index_build",
                "index_update",
                "source",
                "ocr_languages_download",
                "prepare_docling",
                "search",
                "list_models",
                "figure_data",
                "export",
            }:
                request_id = str(request.get("id") or "")
                if not request_id:
                    response = {
                        "id": None,
                        "ok": False,
                        "error": f"{action} requests require an id",
                    }
                else:
                    if action in {
                        "answer",
                        "convert",
                        "batch_convert",
                        "inspect",
                        "source",
                        "ocr_languages_download",
                        "prepare_docling",
                        "search",
                    }:
                        cancel = CancellationToken()
                        with _inflight_lock:
                            _inflight_requests[request_id] = cancel
                        target = _run_cancellable_request
                        args: tuple[Any, ...] = (request, request_id, cancel)
                    else:
                        target = _run_background_request
                        args = (request,)
                    threading.Thread(target=target, args=args, daemon=True).start()
                    continue
            else:
                response = handle(request)
        _write_response(response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
