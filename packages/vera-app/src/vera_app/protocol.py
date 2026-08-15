"""Sidecar action and stream-event names shared with the TypeScript app contract."""

from __future__ import annotations

SIDECAR_ACTIONS = (
    "ping",
    "inspect",
    "validate",
    "index_status",
    "index_build",
    "index_update",
    "search",
    "figure_data",
    "answer",
    "convert",
    "batch_convert",
    "export",
    "source",
    "page",
    "list_models",
    "list_embedding_providers",
    "describe_embedding_providers",
    "list_embedding_models",
    "preflight_embedder",
    "list_ingest_pipelines",
    "describe_ingest_pipelines",
    "ocr_languages_list",
    "ocr_languages_download",
    "list_modes",
    "configure_plugin_runtime",
    "plugin_runtime_status",
    "cancel",
    "skip",
)

STREAM_EVENTS = (
    "search_start",
    "search_done",
    "llm_request",
    "llm_response",
    "tool_call",
    "answer_delta",
    "answer_reset",
    "conversion_progress",
    "index_progress",
    "inspection_progress",
    "ocr_download_progress",
)
