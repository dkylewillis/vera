"""Docling DocumentConverter + HybridChunker ingest pipeline."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import Any

from vera_ingest.cancellation import raise_if_cancelled
from vera_ingest.pipeline import UnknownIngestPipelineError
from vera_ingest.types import IngestRequest, IngestResult, ensure_ingest_request

from . import converter as _converter
from .converter import _build_converter, _split_ocr_languages
from .mapping import WhitespaceTokenizer, map_docling_document
from .options import DoclingOptions
from .recovery import _resolve_conversion

# Compatibility re-exports: tests import these from this module.
__all__ = [
    "DoclingHybridPipeline",
    "WhitespaceTokenizer",
    "map_docling_document",
    "_build_converter",
    "_split_ocr_languages",
]


def _docling_version() -> str:
    try:
        return version("docling")
    except PackageNotFoundError:  # pragma: no cover
        return "unknown"


def _build_diagnostics(
    config: DoclingOptions,
    *,
    effective_backend: str,
    recovered_pages: list[int],
    recovered_pages_backend: dict[int, str],
    whole_document_fallback_backend: str | None,
    whole_document_fallback_strategy: str | None,
) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {
        "engine": "docling",
        "variant": "hybrid",
        "ocr_mode": config.ocr_mode,
        "ocr_language": config.ocr_language,
        "ocr_languages": (
            _split_ocr_languages(config.ocr_language) if config.ocr_mode != "off" else []
        ),
        "images_scale": 1.0,
        "torch_compile": False,
        "overlap_ignored": True,
        "artifacts_path_env": "DOCLING_ARTIFACTS_PATH",
        "pdf_backend": effective_backend,
        "recovered_pages": list(recovered_pages),
    }
    if recovered_pages_backend:
        # JSON-friendly string keys for inspect/sidecar consumers.
        diagnostics["recovered_pages_backend"] = {
            str(page): backend for page, backend in sorted(recovered_pages_backend.items())
        }
    if whole_document_fallback_backend:
        diagnostics["whole_document_fallback_backend"] = whole_document_fallback_backend
    if whole_document_fallback_strategy:
        diagnostics["whole_document_fallback_strategy"] = whole_document_fallback_strategy
    return diagnostics


class DoclingHybridPipeline:
    """Optional Docling parsing pipeline with HybridChunker output.

    Implements ``__call__`` (rather than a named ``ingest`` method) so an
    instance satisfies :data:`vera_ingest.pipeline.IngestPipeline` directly —
    a class is only needed here because Docling's recovery/fallback logic is
    decomposed into helper modules, not because the pipeline holds
    state across calls.
    """

    def __call__(self, source_path: str, options: IngestRequest) -> IngestResult:
        request = ensure_ingest_request(options)
        variant = (request.variant or "hybrid").strip().lower()
        if variant not in {"", "hybrid"}:
            raise UnknownIngestPipelineError(
                f"Unknown Docling pipeline variant {request.variant!r}; use 'docling' or 'docling:hybrid'."
            )
        config = DoclingOptions.from_mapping(request.pipeline_options)
        raise_if_cancelled(request.cancel)

        recovered_pages: list[int] = []
        recovered_pages_backend: dict[int, str] = {}
        whole_document_fallback_backend: str | None = None
        whole_document_fallback_strategy: str | None = None
        effective_backend = config.pdf_backend

        # Users who force pypdfium2 skip docling_parse retries during recovery.
        primary_backend = config.pdf_backend
        conversion: Any | None = None
        primary_raised = False
        primary_error: BaseException | None = None
        try:
            converter = _converter._build_converter(config, backend=primary_backend)
            conversion = converter.convert(source=source_path, raises_on_error=False)
        except Exception as exc:  # noqa: BLE001 - Docling may raise on hard native crashes
            if _converter._is_cancellation(exc):
                raise
            primary_raised = True
            primary_error = exc
            conversion = None
            _converter._log_convert_failure(primary_backend, None, exc)

        raise_if_cancelled(request.cancel)
        mapped = _resolve_conversion(
            source_path=source_path,
            config=config,
            conversion=conversion,
            primary_backend=primary_backend,
            primary_raised=primary_raised,
            cancel=request.cancel,
            recovered_pages=recovered_pages,
            recovered_pages_backend=recovered_pages_backend,
            primary_error=primary_error,
        )
        if mapped.whole_fallback:
            whole_document_fallback_backend = mapped.whole_fallback
            whole_document_fallback_strategy = mapped.fallback_strategy
            effective_backend = mapped.whole_fallback

        return IngestResult(
            pages=mapped.pages,
            blocks=mapped.blocks,
            chunks=mapped.chunks,
            parser_name="docling",
            parser_version=_docling_version(),
            chunking_strategy=f"docling_hybrid:{int(config.chunk_size)}",
            diagnostics=_build_diagnostics(
                config,
                effective_backend=effective_backend,
                recovered_pages=recovered_pages,
                recovered_pages_backend=recovered_pages_backend,
                whole_document_fallback_backend=whole_document_fallback_backend,
                whole_document_fallback_strategy=whole_document_fallback_strategy,
            ),
        )
