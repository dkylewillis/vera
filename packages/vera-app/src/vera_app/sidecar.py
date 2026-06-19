from __future__ import annotations

import base64
import json
import sys
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

from vera import VeraDocument, convert
from vera.corpus import VeraCorpus

Request = dict[str, Any]
Response = dict[str, Any]
Handler = Callable[[Request], Any]


def _open_document(path: str) -> VeraDocument:
    return VeraDocument.open(path)


def _figure_payload(figure: dict[str, Any]) -> dict[str, Any]:
    data = figure.pop("data", None)
    if data is not None:
        mime_type = figure.get("mime_type") or "application/octet-stream"
        figure["data_url"] = f"data:{mime_type};base64,{base64.b64encode(data).decode('ascii')}"
    return figure


def _inspect(request: Request) -> dict[str, Any]:
    path = str(request["path"])
    if Path(path).is_dir():
        corpus = VeraCorpus.open(path)
        try:
            return corpus.inspect()
        finally:
            corpus.close()
    doc = _open_document(path)
    try:
        return doc.inspect()
    finally:
        doc.close()


def _validate(request: Request) -> dict[str, Any]:
    doc = _open_document(str(request["path"]))
    try:
        return doc.validate()
    finally:
        doc.close()


def _search(request: Request) -> list[dict[str, Any]]:
    path = str(request["path"])
    target = VeraCorpus.open(path) if Path(path).is_dir() else _open_document(path)
    try:
        results = target.search(
            str(request.get("query", "")),
            mode=str(request.get("mode", "hybrid")),
            top_k=int(request.get("top_k", 10)),
            context_chunks=int(request.get("context_chunks", 0)),
        )
        include_regions = bool(request.get("include_regions", False))
        include_figures = bool(request.get("include_figures", False))
        include_figure_data = bool(request.get("include_figure_data", False))
        payload: list[dict[str, Any]] = []
        for result in results:
            entry = result.as_dict()
            if include_regions:
                entry["regions"] = target.regions_for(result)
            if include_figures:
                entry["figures"] = [_figure_payload(figure) for figure in target.figures_for(result, include_data=include_figure_data)]
            payload.append(entry)
        return payload
    finally:
        target.close()


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


def _export(request: Request) -> dict[str, Any]:
    doc = _open_document(str(request["path"]))
    try:
        output = doc.export_source_document(str(request["output"]) if request.get("output") else None)
        source = doc.get_source_document()
        return {
            "output": output,
            "filename": source.filename,
            "mime_type": source.mime_type,
            "hash": source.hash,
        }
    finally:
        doc.close()


def _source(request: Request) -> dict[str, Any]:
    doc = _open_document(str(request["path"]))
    try:
        source = doc.get_source_document()
        mime_type = source.mime_type or "application/octet-stream"
        return {
            "filename": source.filename,
            "mime_type": mime_type,
            "hash": source.hash,
            "size": len(source.data),
            "data_url": f"data:{mime_type};base64,{base64.b64encode(source.data).decode('ascii')}",
        }
    finally:
        doc.close()


def _page(request: Request) -> dict[str, Any] | None:
    doc = _open_document(str(request["path"]))
    try:
        return doc.get_page(int(request["page_number"]))
    finally:
        doc.close()


HANDLERS: dict[str, Handler] = {
    "ping": lambda request: {"status": "ok"},
    "inspect": _inspect,
    "validate": _validate,
    "search": _search,
    "convert": _convert,
    "export": _export,
    "source": _source,
    "page": _page,
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
