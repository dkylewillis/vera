"""Minimal ingest plugin used to verify entry-point discovery."""

from __future__ import annotations

from typing import Any

from vera_ingest.pipeline import PipelineDescriptor, UnknownIngestPipelineError


def create_pipeline(variant: str = ""):
    normalized = (variant or "").strip().lower()
    if normalized not in {"", "default"}:
        raise UnknownIngestPipelineError(
            f"Unknown echo pipeline variant {variant!r}; use 'echo'."
        )

    def ingest(source_path: str, output_path: str, **options: Any) -> str:
        from vera_ingest.convert import convert_with_pymupdf

        filtered = {
            key: value
            for key, value in options.items()
            if key in {
                "model",
                "chunk_size",
                "overlap",
                "store_original",
                "ocr_mode",
                "ocr_language",
                "ocr_dpi",
                "cancel",
            }
        }
        return convert_with_pymupdf(source_path, output_path, **filtered)

    return ingest


def create_descriptor(variant: str = "") -> PipelineDescriptor:
    del variant
    return PipelineDescriptor(
        provider="echo",
        spec="echo",
        label="echo — test ingest plugin",
        description="Test plugin used by VERA plugin-host tests.",
        installed=True,
    )
