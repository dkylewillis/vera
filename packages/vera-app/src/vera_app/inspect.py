"""Inspect, validate, and page-text sidecar handlers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vera_app.cancellation import CancellationToken
from vera_app.documents import open_corpus, open_document
from vera_app.types import Request, WriteEvent
from vera_ingest.viewer import get_page


def inspect(
    request: Request,
    write_event: WriteEvent | None = None,
    cancel: CancellationToken | None = None,
) -> dict[str, Any]:
    if cancel:
        cancel.raise_if_cancelled()
    path = str(request["path"])
    if Path(path).is_dir():
        corpus = open_corpus(path, request)
        try:
            if request.get("summary_only"):
                result = corpus.inspect_summary()
                if cancel:
                    cancel.raise_if_cancelled()
                return result

            def report_progress(update: dict[str, Any]) -> None:
                if cancel:
                    cancel.raise_if_cancelled()
                if write_event:
                    write_event({"event": "inspection_progress", **update})

            return corpus.inspect(
                progress=report_progress if write_event or cancel else None,
            )
        finally:
            corpus.close()
    doc = open_document(path)
    try:
        result = doc.inspect()
        if cancel:
            cancel.raise_if_cancelled()
        return result
    finally:
        doc.close()


def validate(request: Request) -> dict[str, Any]:
    doc = open_document(str(request["path"]))
    try:
        return doc.validate()
    finally:
        doc.close()


def page(request: Request) -> dict[str, Any] | None:
    doc = open_document(str(request["path"]))
    try:
        return get_page(doc, int(request["page_number"]))
    finally:
        doc.close()
