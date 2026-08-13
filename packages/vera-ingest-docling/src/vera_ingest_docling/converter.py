"""DocumentConverter construction and PDF backend selection."""

from __future__ import annotations

from typing import Any

from .options import DoclingOptions

_PDF_BACKEND_DOCLING_PARSE = "docling_parse"
_PDF_BACKEND_PYPDFIUM2 = "pypdfium2"


def _split_ocr_languages(ocr_language: str) -> list[str]:
    """Split a ``+``/``,``-joined RapidOCR-native language string into codes.

    No translation or validation against a known set happens here — VERA no
    longer maintains a Tesseract-to-RapidOCR alias table; an unrecognized
    code is rejected by RapidOCR itself when OCR actually runs.
    """
    parts = [part.strip().lower() for part in (ocr_language or "en").replace("+", ",").split(",")]
    codes = [part for part in parts if part]
    return codes or ["en"]


def _disable_torch_compile() -> None:
    """Avoid torch.compile / Inductor, which requires MSVC ``cl.exe`` on Windows.

    Docling enables ``compile_torch_models`` by default. On machines without Visual
    Studio Build Tools that fails page-by-page with \"Compiler: cl is not found\"
    and often cascades into memory exhaustion.
    """
    try:
        from docling.datamodel.settings import settings

        settings.inference.compile_torch_models = False
    except Exception:  # pragma: no cover - defensive against Docling API drift
        pass
    try:
        import torch._dynamo

        torch._dynamo.config.suppress_errors = True
    except Exception:  # pragma: no cover - torch optional at import time
        pass


def _build_converter(options: DoclingOptions, *, backend: str | None = None) -> Any:
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    ocr_mode = options.ocr_mode
    # Must run before PdfPipelineOptions() so default_factory compile flags are False.
    _disable_torch_compile()

    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_table_structure = True
    pipeline_options.generate_picture_images = True
    # Keep Docling's default raster scale. Mapping VERA's Tesseract OCR DPI
    # (default 300) to images_scale (~4.17x) OOMs large manuals.
    pipeline_options.images_scale = 1.0
    layout_engine = getattr(getattr(pipeline_options, "layout_options", None), "engine_options", None)
    if layout_engine is not None and hasattr(layout_engine, "compile_model"):
        layout_engine.compile_model = False

    if ocr_mode == "off":
        pipeline_options.do_ocr = False
    else:
        pipeline_options.do_ocr = True
        ocr_options = RapidOcrOptions(
            force_full_page_ocr=(ocr_mode == "force"),
            lang=_split_ocr_languages(options.ocr_language),
        )
        pipeline_options.ocr_options = ocr_options

    selected = (backend or options.pdf_backend or _PDF_BACKEND_DOCLING_PARSE).strip().lower()
    format_kwargs: dict[str, Any] = {"pipeline_options": pipeline_options}
    if selected == _PDF_BACKEND_PYPDFIUM2:
        from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend

        format_kwargs["backend"] = PyPdfiumDocumentBackend

    return DocumentConverter(
        allowed_formats=[InputFormat.PDF],
        format_options={
            InputFormat.PDF: PdfFormatOption(**format_kwargs),
        },
    )


def _is_cancellation(exc: BaseException) -> bool:
    """True for sidecar cancel/skip errors (RuntimeError subclasses)."""
    return any(
        cls.__name__ in {"CancelledError", "SkipCurrentError"}
        for cls in type(exc).mro()
    )


def _try_convert(
    source_path: str,
    config: DoclingOptions,
    *,
    backend: str,
    page_range: tuple[int, int] | None = None,
) -> Any | None:
    """Run one Docling convert; return the ConversionResult or None on hard failure.

    ``raises_on_error=False`` lets Docling return PARTIAL_SUCCESS instead of
    re-raising page-batch OOMs. Native crashes still raise and become None
    here (except cancel/skip, which propagate).
    """
    converter = _build_converter(config, backend=backend)
    kwargs: dict[str, Any] = {"source": source_path, "raises_on_error": False}
    if page_range is not None:
        kwargs["page_range"] = page_range
    try:
        return converter.convert(**kwargs)
    except Exception as exc:  # noqa: BLE001 - catch native/process crashes from Docling
        if _is_cancellation(exc):
            raise
        return None
