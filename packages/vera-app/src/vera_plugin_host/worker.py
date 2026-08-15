"""JSON-lines ingest worker: discovery, convert, batch convert, cancel/skip."""

from __future__ import annotations

import base64
import json
import sys
import threading
import traceback
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from vera_doc import (
    get_embedder,
    list_embedding_models,
    list_embedding_provider_descriptors,
    list_embedding_providers,
    preflight_embedder,
)
from vera_doc.embeddings import serialize_vector
from vera_ingest import batch_convert, convert
from vera_ingest.pipeline import (
    PLUGIN_API_VERSION,
    list_ingest_pipeline_descriptors,
    list_ingest_pipeline_load_errors,
    list_ingest_pipelines,
)

from .cancellation import CancellationToken, CancelledError, SkipCurrentError

PROTOCOL_VERSION = 2
Request = dict[str, Any]
Response = dict[str, Any]
Handler = Callable[..., Any]
_THREADED_ACTIONS = {"convert", "batch_convert", "embed", "embedder_info"}

_CONVERT_ALIAS_CASTERS = (
    ("chunk_size", int),
    ("overlap", int),
    ("ocr_mode", str),
    ("ocr_language", str),
    ("ocr_dpi", int),
    ("ocr_download", bool),
)


def _ingest_version() -> str:
    try:
        return version("vera-ingest")
    except PackageNotFoundError:
        return "unknown"


def _doc_version() -> str:
    try:
        return version("vera-doc")
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
        "vera_doc_version": _doc_version(),
        "pipelines": list_ingest_pipelines(),
        "embedders": list_embedding_providers(),
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
    """Match sidecar convert forwarding without importing vera_app or OCR."""
    kwargs: dict[str, Any] = {
        "model": str(request.get("model", "hashing")),
        "parser": str(request.get("parser", "pymupdf")),
        "store_original": bool(request.get("store_original", True)),
    }
    raw_pipeline_options = request.get("pipeline_options")
    if isinstance(raw_pipeline_options, dict):
        kwargs["pipeline_options"] = dict(raw_pipeline_options)
    raw_embedder_options = request.get("embedder_options")
    if isinstance(raw_embedder_options, dict):
        kwargs["embedder_options"] = dict(raw_embedder_options)
    for key, caster in _CONVERT_ALIAS_CASTERS:
        if key in request:
            kwargs[key] = caster(request[key])
    return kwargs


def _require_ready_embedder(model: str) -> None:
    result = preflight_embedder(model)
    if not result.ok:
        raise ValueError(result.detail or "Embedding provider is not ready")


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
    kwargs = _convert_kwargs(request)
    _require_ready_embedder(str(kwargs.get("model") or "hashing"))
    output = convert(
        input_path,
        str(request["output"]),
        cancel=cancel,
        **kwargs,
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

    kwargs = _convert_kwargs(request)
    _require_ready_embedder(str(kwargs.get("model") or "hashing"))
    return batch_convert(
        None if paths is not None else str(directory),
        paths=paths,
        recursive=bool(request.get("recursive", True)),
        overwrite=bool(request.get("overwrite", False)),
        progress=report_progress,
        cancel=cancel,
        **kwargs,
    )


def handle_list_embedding_providers(_request: Request) -> dict[str, Any]:
    return {"providers": list_embedding_providers()}


def handle_describe_embedding_providers(_request: Request) -> dict[str, Any]:
    return {
        "providers": [item.as_dict() for item in list_embedding_provider_descriptors()],
    }


def handle_list_embedding_models(request: Request) -> dict[str, Any]:
    provider = str(request.get("provider") or "").strip()
    if not provider:
        raise ValueError("provider is required")
    return {
        "provider": provider,
        "models": [item.as_dict() for item in list_embedding_models(provider)],
    }


def handle_preflight_embedder(request: Request) -> dict[str, Any]:
    model = str(request.get("model") or "hashing")
    return preflight_embedder(model).as_dict()


def _embedder_from_request(request: Request) -> Any:
    raw_options = request.get("embedder_options")
    options = dict(raw_options) if isinstance(raw_options, dict) else None
    return get_embedder(str(request.get("model") or "hashing"), embedder_options=options)


def handle_embedder_info(
    request: Request,
    write_event: Callable[[dict[str, Any]], None] | None = None,
    cancel: CancellationToken | None = None,
) -> dict[str, Any]:
    if cancel:
        cancel.raise_if_cancelled()
    embedder = _embedder_from_request(request)
    if cancel:
        cancel.raise_if_cancelled()
    return {
        "model_name": str(getattr(embedder, "model_name", "")),
        "dimension": int(embedder.dimension),
        "normalization": str(getattr(embedder, "normalization", "unknown") or "unknown"),
    }


def handle_embed(
    request: Request,
    write_event: Callable[[dict[str, Any]], None] | None = None,
    cancel: CancellationToken | None = None,
) -> dict[str, Any]:
    if cancel:
        cancel.raise_if_cancelled()
    raw_texts = request.get("texts")
    if not isinstance(raw_texts, list) or not raw_texts:
        raise ValueError("texts must be a non-empty list")
    texts = [str(item) for item in raw_texts]
    embedder = _embedder_from_request(request)
    if cancel:
        cancel.raise_if_cancelled()
    vectors = embedder.embed(texts)
    encoded = [
        base64.b64encode(serialize_vector(vector)).decode("ascii")
        for vector in vectors
    ]
    return {
        "vectors": encoded,
        "model_name": str(getattr(embedder, "model_name", "")),
        "dimension": int(embedder.dimension),
        "normalization": str(getattr(embedder, "normalization", "unknown") or "unknown"),
    }


HANDLERS: dict[str, Handler] = {
    "ping": handle_ping,
    "list_ingest_pipelines": handle_list_ingest_pipelines,
    "describe_ingest_pipelines": handle_describe_ingest_pipelines,
    "list_embedding_providers": handle_list_embedding_providers,
    "describe_embedding_providers": handle_describe_embedding_providers,
    "list_embedding_models": handle_list_embedding_models,
    "preflight_embedder": handle_preflight_embedder,
    "embedder_info": handle_embedder_info,
    "embed": handle_embed,
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
    if action in {"embed", "embedder_info"}:
        return "Embedding cancelled"
    return "Request cancelled"


def handle(request: Request, cancel: CancellationToken | None = None) -> Response:
    request_id = request.get("id")
    action = str(request.get("action", ""))
    try:
        if action not in HANDLERS:
            raise ValueError(f"Unknown action: {action}")
        if action in _THREADED_ACTIONS:

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
            elif action in _THREADED_ACTIONS:
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
