"""Classify stored .vera keys into format, convert, and pipeline layers."""

from __future__ import annotations

from typing import Any

# vera_metadata keys from the 0.2 format. archive_metadata is the caller's object.
FORMAT_HEADER_KEYS = (
    "format_name",
    "format_version",
    "created_at",
    "created_by",
    "creator_library",
    "default_embedding_model",
    "default_embedding_dimension",
    "default_embedding_normalization",
)

# Keys vera convert writes into archive_metadata. Anything else there was
# passed by the caller (--metadata) or is an attachment id convert adds.
CONVERT_ARCHIVE_KEYS = frozenset(
    {
        "title",
        "source_file_name",
        "source_file_hash",
        "source_mime_type",
        "chunking_strategy",
        "parser_name",
        "parser_version",
        "ocr",
        "page_count",
        "viewer_pages_attachment_id",
        "viewer_blocks_attachment_id",
        "viewer_preview_attachment_id",
        "source_attachment_id",
        "ingest_warnings",
        "ingest_notes",
    }
)

# Conventional chunk metadata. The format does not require them; convert writes them.
BASE_CHUNK_KEYS = frozenset(
    {
        "document_id",
        "source_filename",
        "page_start",
        "page_end",
        "heading_path",
        "token_count",
        "regions",
    }
)

TABLES = {
    "vera_metadata": ["key", "value"],
    "chunks": ["chunk_id", "text", "metadata_json", "created_at", "updated_at"],
    "embeddings": [
        "chunk_id",
        "model_name",
        "model_dimension",
        "vector",
        "vector_format",
        "created_at",
    ],
    "attachments": [
        "attachment_id",
        "mime_type",
        "filename",
        "data",
        "hash",
        "metadata_json",
        "created_at",
    ],
    "chunk_attachments": ["chunk_id", "attachment_id", "role"],
    "chunks_fts": ["chunk_id", "text"],
}


def build_key_schema(
    *,
    header: dict[str, Any] | None = None,
    archive_metadata: dict[str, Any] | None = None,
    chunk_metadata: list[dict[str, Any]] | None = None,
    parser_name: str = "",
    parser_version: str = "",
) -> dict[str, Any]:
    """Return stored key names, split by who writes them."""
    header = header or {}
    archive_metadata = archive_metadata or {}
    records = [item for item in (chunk_metadata or []) if isinstance(item, dict)]

    format_keys = {
        key: header[key]
        for key in FORMAT_HEADER_KEYS
        if header.get(key) not in (None, "")
    }
    convert_keys: dict[str, Any] = {}
    caller_keys: dict[str, Any] = {}
    for key, value in archive_metadata.items():
        if value is None:
            continue
        if key in CONVERT_ARCHIVE_KEYS or key.endswith("_attachment_id"):
            convert_keys[key] = value
        else:
            caller_keys[key] = value

    present_base: set[str] = set()
    region_keys: set[str] = set()
    pipeline_stats: dict[str, dict[str, Any]] = {}
    for metadata in records:
        record_type = metadata.get("record_type")
        record_label = record_type if isinstance(record_type, str) and record_type else ""
        for key, value in metadata.items():
            if key in BASE_CHUNK_KEYS:
                present_base.add(key)
                if key == "regions" and isinstance(value, list):
                    for region in value:
                        if isinstance(region, dict):
                            region_keys.update(str(name) for name in region)
                continue
            stat = pipeline_stats.setdefault(
                key,
                {"chunks": 0, "values": {}, "record_types": set()},
            )
            stat["chunks"] += 1
            if record_label:
                stat["record_types"].add(record_label)
            if isinstance(value, (str, int, float, bool)) and not isinstance(value, bool):
                text = str(value)
                if len(text) <= 48:
                    counts: dict[str, int] = stat["values"]
                    counts[text] = counts.get(text, 0) + 1
            elif isinstance(value, bool):
                text = "true" if value else "false"
                counts = stat["values"]
                counts[text] = counts.get(text, 0) + 1

    pipeline_keys = []
    for key in sorted(pipeline_stats):
        stat = pipeline_stats[key]
        values: dict[str, int] = stat["values"]
        entry: dict[str, Any] = {"key": key, "chunks": stat["chunks"]}
        if values and len(values) <= 12 and all(len(name) <= 48 for name in values):
            entry["values"] = dict(sorted(values.items(), key=lambda item: (-item[1], item[0])))
        record_types = sorted(stat["record_types"])
        if record_types:
            entry["record_types"] = record_types
        pipeline_keys.append(entry)

    parser_name = str(archive_metadata.get("parser_name") or parser_name or "")
    parser_version = str(archive_metadata.get("parser_version") or parser_version or "")
    return {
        "format_keys": format_keys,
        "convert_keys": convert_keys,
        "caller_keys": caller_keys,
        "base_chunk_keys": sorted(present_base),
        "region_keys": sorted(region_keys),
        "pipeline": {
            "name": parser_name,
            "version": parser_version,
            "keys": pipeline_keys,
        },
        "tables": TABLES,
    }
