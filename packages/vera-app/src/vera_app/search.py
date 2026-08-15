"""Search and figure-payload sidecar handlers."""

from __future__ import annotations

from typing import Any

from vera_app.cancellation import CancellationToken
from vera_app.documents import open_document, resolve_target, scoped_single_file
from vera_app.types import Request
from vera_doc.corpus import VeraCorpus
from vera_ingest.viewer import figure_data_url, figures, result_payload


def search_report(request: Request, cancel: CancellationToken | None = None) -> dict[str, Any]:
    if cancel:
        cancel.raise_if_cancelled()
    target = resolve_target(request)
    # When the search is scoped to a single file, stamp each result with its
    # source path so the UI can open/highlight it (corpus results already carry
    # `file`; single-document results otherwise don't).
    scoped_file = scoped_single_file(request)
    try:
        results = target.search(
            text=str(request.get("query", "")),
            mode=str(request.get("mode", "hybrid")),
            top_k=int(request.get("top_k", 10)),
            context_chunks=int(request.get("context_chunks", 0)),
        )
        if cancel:
            cancel.raise_if_cancelled()
        include_regions = bool(request.get("include_regions", False))
        include_figures = bool(request.get("include_figures", False))
        include_figure_data = bool(request.get("include_figure_data", False))
        payload: list[dict[str, Any]] = []
        for result in results:
            if cancel:
                cancel.raise_if_cancelled()
            document = target.document(result.file) if isinstance(target, VeraCorpus) else target
            entry = result_payload(
                result,
                document=document,
                include_figures=include_figures,
                include_regions=include_regions,
                figure_data_urls=include_figure_data,
            )
            if scoped_file and not entry.get("file"):
                entry["file"] = scoped_file
            payload.append(entry)
        skipped = list(getattr(target, "skipped_semantic_model_groups", []) or [])
        return {"results": payload, "skipped_semantic_model_groups": skipped}
    finally:
        target.close()


def search(request: Request, cancel: CancellationToken | None = None) -> list[dict[str, Any]]:
    return search_report(request, cancel=cancel)["results"]


def figure_data(request: Request) -> list[dict[str, Any]]:
    """Return image payloads for explicitly selected figure attachments."""
    raw_ids = request.get("asset_ids")
    asset_ids = (
        list(dict.fromkeys(str(value) for value in raw_ids if str(value).strip()))
        if isinstance(raw_ids, list)
        else []
    )
    if not asset_ids:
        return []
    doc = open_document(str(request["path"]))
    try:
        return [
            figure_data_url(figure)
            for figure in figures(
                doc,
                include_data=True,
                attachment_ids=asset_ids,
            )
        ]
    finally:
        doc.close()
