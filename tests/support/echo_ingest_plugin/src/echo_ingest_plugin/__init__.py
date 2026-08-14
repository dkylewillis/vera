"""Minimal ingest plugin used to verify entry-point discovery."""

from __future__ import annotations

from pathlib import Path

from vera_ingest.descriptors import PipelineDescriptor
from vera_ingest.pipeline import UnknownIngestPipelineError
from vera_ingest.types import IngestBlock, IngestChunk, IngestRequest, IngestResult, ParsedPage


def create_pipeline(variant: str = ""):
    normalized = (variant or "").strip().lower()
    if normalized not in {"", "default"}:
        raise UnknownIngestPipelineError(
            f"Unknown echo pipeline variant {variant!r}; use 'echo'."
        )

    def ingest(source_path: str, request: IngestRequest) -> IngestResult:
        del request
        path = Path(source_path)
        text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else "echo"
        if not text.strip():
            text = "echo"
        return IngestResult(
            pages=[ParsedPage(page_number=1, width=612, height=792, text=text)],
            blocks=[
                IngestBlock(
                    block_id="b1",
                    page_number=1,
                    block_type="paragraph",
                    text=text,
                )
            ],
            chunks=[
                IngestChunk(
                    chunk_id="c1",
                    text=text,
                    page_start=1,
                    page_end=1,
                    heading_path="",
                    token_count=len(text.split()),
                    block_ids=["b1"],
                )
            ],
            parser_name="echo",
            parser_version="0.0.1",
            chunking_strategy="passthrough",
        )

    return ingest


def create_descriptor(variant: str = "") -> PipelineDescriptor:
    del variant
    return PipelineDescriptor(
        provider="echo",
        variant="",
        spec="echo",
        label="echo — test ingest plugin",
        description="Test plugin used by VERA plugin-host tests.",
        installed=True,
    )
