from __future__ import annotations

import json
import sys
import traceback
from collections.abc import Callable
from typing import Any

from vera import VeraDocument, convert

Request = dict[str, Any]
Response = dict[str, Any]
Handler = Callable[[Request], Any]


def _open_document(path: str) -> VeraDocument:
    return VeraDocument.open(path)


def _inspect(request: Request) -> dict[str, Any]:
    with_document = _open_document(str(request["path"]))
    try:
        return with_document.inspect()
    finally:
        with_document.close()


def _validate(request: Request) -> dict[str, Any]:
    doc = _open_document(str(request["path"]))
    try:
        return doc.validate()
    finally:
        doc.close()


def _search(request: Request) -> list[dict[str, Any]]:
    doc = _open_document(str(request["path"]))
    try:
        results = doc.search(
            str(request.get("query", "")),
            mode=str(request.get("mode", "hybrid")),
            top_k=int(request.get("top_k", 10)),
            context_chunks=int(request.get("context_chunks", 0)),
        )
        include_regions = bool(request.get("include_regions", False))
        include_figures = bool(request.get("include_figures", False))
        payload: list[dict[str, Any]] = []
        for result in results:
            entry = result.as_dict()
            if include_regions:
                entry["regions"] = doc.regions_for(result)
            if include_figures:
                entry["figures"] = doc.figures_for(result)
            payload.append(entry)
        return payload
    finally:
        doc.close()


def _convert(request: Request) -> dict[str, str]:
    output = convert(
        str(request["input"]),
        str(request["output"]),
        model=str(request.get("model", "hashing")),
        parser=str(request.get("parser", "pymupdf")),
        chunk_size=int(request.get("chunk_size", 500)),
        overlap=int(request.get("overlap", 75)),
        store_original=bool(request.get("store_original", True)),
    )
    return {"output": output}


HANDLERS: dict[str, Handler] = {
    "ping": lambda request: {"status": "ok"},
    "inspect": _inspect,
    "validate": _validate,
    "search": _search,
    "convert": _convert,
}


def handle(request: Request) -> Response:
    request_id = request.get("id")
    try:
        action = str(request.get("action", ""))
        if action not in HANDLERS:
            raise ValueError(f"Unknown action: {action}")
        return {"id": request_id, "ok": True, "result": HANDLERS[action](request)}
    except Exception as exc:
        return {
            "id": request_id,
            "ok": False,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            response: Response = {"id": None, "ok": False, "error": str(exc)}
        else:
            response = handle(request)
        print(json.dumps(response), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
