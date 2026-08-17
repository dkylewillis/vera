"""DocumentConverter construction and PDF backend selection."""

from __future__ import annotations

import os
import sys
import threading
import traceback
from pathlib import Path
from typing import Any

from .options import DoclingOptions

_PDF_BACKEND_DOCLING_PARSE = "docling_parse"
_PDF_BACKEND_PYPDFIUM2 = "pypdfium2"

# Filenames RapidOCR ships in `rapidocr/models` and Docling looks for under
# `{DOCLING_ARTIFACTS_PATH}/RapidOcr` when artifacts_path is set.
_RAPIDOCR_MODEL_FILES = {
    "det_model_path": "PP-OCRv6_det_small.onnx",
    "cls_model_path": "ch_ppocr_mobile_v2.0_cls_mobile.onnx",
    "rec_model_path": "PP-OCRv6_rec_small.onnx",
}


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


def _rapidocr_paths_from_dir(directory: Path) -> dict[str, str]:
    paths = {key: directory / name for key, name in _RAPIDOCR_MODEL_FILES.items()}
    if all(path.is_file() for path in paths.values()):
        return {key: str(path) for key, path in paths.items()}
    return {}


def _rapidocr_model_paths() -> dict[str, str]:
    """Locate RapidOCR ONNX weights without requiring a Docling artifacts cache.

    Setting ``DOCLING_ARTIFACTS_PATH`` makes Docling treat RapidOCR as
    fully-offline: it looks under ``<artifacts>/RapidOcr`` and raises if those
    files are missing, even when ``docling[rapidocr]`` already installed them
    into site-packages. Prefer a complete artifacts copy when present; otherwise
    pin the packaged model paths so the desktop app cache can hold layout
    models without also prefetching RapidOCR.
    """
    artifacts = (os.environ.get("DOCLING_ARTIFACTS_PATH") or "").strip()
    if artifacts:
        cached = _rapidocr_paths_from_dir(Path(artifacts) / "RapidOcr")
        if cached:
            return cached
    try:
        import rapidocr
    except ImportError:
        return {}
    package_root = Path(rapidocr.__file__).resolve().parent
    return _rapidocr_paths_from_dir(package_root / "models")


# Docling offline layout: repo id with "/" replaced by "--".
_LAYOUT_MODEL_DIR = "docling-project--docling-layout-heron"
_TABLEFORMER_MODEL_DIR = "docling-project--docling-models"
_WEIGHT_SUFFIXES = {".safetensors", ".bin", ".onnx", ".pt", ".pth"}
_MODEL_DOWNLOAD_LOCK = threading.Lock()


def _has_incomplete_download(directory: Path) -> bool:
    return any(path.name.endswith(".incomplete") for path in directory.rglob("*"))


def _has_weight_file(directory: Path) -> bool:
    return any(
        path.is_file() and path.suffix.lower() in _WEIGHT_SUFFIXES and path.stat().st_size > 0
        for path in directory.rglob("*")
    )


def _layout_model_cached(artifacts: Path) -> bool:
    """True when Heron exists as a complete Docling artifacts snapshot.

    A non-empty folder is not enough: stopping mid-download can leave
    ``config.json`` without weights, and treating that as cached would lock
    later runs into offline mode.
    """
    heron = artifacts / _LAYOUT_MODEL_DIR
    if not heron.is_dir() or _has_incomplete_download(heron):
        return False
    config = heron / "config.json"
    return config.is_file() and config.stat().st_size > 0 and _has_weight_file(heron)


def _tableformer_cached(artifacts: Path) -> bool:
    root = artifacts / _TABLEFORMER_MODEL_DIR
    if not root.is_dir() or _has_incomplete_download(root):
        return False
    return any(
        path.is_file() and path.name == "tm_config.json" and path.stat().st_size > 0
        for path in root.rglob("tm_config.json")
    )


def _docling_models_ready(artifacts: Path) -> bool:
    """Layout and TableFormer must both be complete before going fully offline."""
    return _layout_model_cached(artifacts) and _tableformer_cached(artifacts)


def _download_docling_models(artifacts: Path) -> None:
    """Fetch the models VERA's Docling pipeline actually loads.

    RapidOCR ONNX weights are pinned from site-packages separately. Code,
    picture-classifier, and VLM extras are not enabled on this pipeline.
    """
    from docling.utils.model_downloader import download_models

    download_models(
        output_dir=artifacts,
        progress=True,
        with_layout=True,
        with_tableformer=True,
        with_tableformer_v2=False,
        with_code_formula=False,
        with_picture_classifier=False,
        with_rapidocr=False,
        with_easyocr=False,
        with_nemotron_ocr=False,
    )


def _configure_docling_artifacts() -> None:
    """Use artifacts_path only when layout and table models are cached there.

    Docling treats ``DOCLING_ARTIFACTS_PATH`` as fully offline: a missing
    Heron or TableFormer folder raises instead of downloading. When the cache
    is incomplete, clear ``settings.artifacts_path`` so Hugging Face can
    download or resume, and keep ``HF_HOME`` inside the same directory.
    """
    try:
        from docling.datamodel.settings import settings
    except Exception:  # pragma: no cover - Docling optional at import time
        return
    raw = (os.environ.get("DOCLING_ARTIFACTS_PATH") or "").strip()
    if not raw:
        return
    artifacts = Path(raw)
    artifacts.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", raw)
    if _docling_models_ready(artifacts):
        settings.artifacts_path = artifacts
        return
    settings.artifacts_path = None


def ensure_docling_models() -> dict[str, Any]:
    """Prefetch layout and table models into ``DOCLING_ARTIFACTS_PATH``.

    Idempotent and process-locked so Convert and a desktop prepare request
    cannot download the same snapshot twice. Incomplete caches stay online
    (Hub resume) instead of being treated as a ready offline tree.
    """
    _configure_docling_artifacts()
    raw = (os.environ.get("DOCLING_ARTIFACTS_PATH") or "").strip()
    if not raw:
        return {"ready": False, "downloaded": False, "reason": "no_artifacts_path"}
    artifacts = Path(raw)
    if _docling_models_ready(artifacts):
        return {"ready": True, "downloaded": False, "artifacts_path": str(artifacts)}
    with _MODEL_DOWNLOAD_LOCK:
        _configure_docling_artifacts()
        if _docling_models_ready(artifacts):
            return {"ready": True, "downloaded": False, "artifacts_path": str(artifacts)}
        print(
            "Docling layout models are not in the artifacts cache yet; "
            "downloading from Hugging Face (first run can take several minutes). "
            "Stopping mid-download does not abort Hugging Face immediately; "
            "the next run will resume.",
            file=sys.stderr,
            flush=True,
        )
        _download_docling_models(artifacts)
        _configure_docling_artifacts()
        return {
            "ready": _docling_models_ready(artifacts),
            "downloaded": True,
            "artifacts_path": str(artifacts),
        }


def _build_converter(options: DoclingOptions, *, backend: str | None = None) -> Any:
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    ocr_mode = options.ocr_mode
    # Must run before PdfPipelineOptions() so default_factory compile flags are False.
    _disable_torch_compile()
    ensure_docling_models()

    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_table_structure = True
    pipeline_options.generate_picture_images = True
    # Keep Docling's default raster scale. Mapping VERA's Tesseract OCR DPI
    # (default 300) to images_scale (~4.17x) OOMs large manuals.
    pipeline_options.images_scale = 1.0
    layout_engine = getattr(
        getattr(pipeline_options, "layout_options", None), "engine_options", None
    )
    if layout_engine is not None and hasattr(layout_engine, "compile_model"):
        layout_engine.compile_model = False

    if ocr_mode == "off":
        pipeline_options.do_ocr = False
    else:
        pipeline_options.do_ocr = True
        ocr_kwargs: dict[str, Any] = {
            "force_full_page_ocr": ocr_mode == "force",
            "lang": _split_ocr_languages(options.ocr_language),
        }
        ocr_kwargs.update(_rapidocr_model_paths())
        pipeline_options.ocr_options = RapidOcrOptions(**ocr_kwargs)

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
    return any(cls.__name__ in {"CancelledError", "SkipCurrentError"} for cls in type(exc).mro())


def _log_convert_failure(
    backend: str,
    page_range: tuple[int, int] | None,
    exc: BaseException,
) -> None:
    """Print convert failures to stderr so `app:dev` shows `[vera-sidecar]` lines."""
    pages = f"{page_range[0]}-{page_range[1]}" if page_range is not None else "all"
    print(
        f"Docling convert failed (backend={backend}, pages={pages}): {type(exc).__name__}: {exc}",
        file=sys.stderr,
        flush=True,
    )
    traceback.print_exception(type(exc), exc, exc.__traceback__, file=sys.stderr)


def _try_convert(
    source_path: str,
    config: DoclingOptions,
    *,
    backend: str,
    page_range: tuple[int, int] | None = None,
    converter: Any | None = None,
) -> tuple[Any | None, BaseException | None]:
    """Run one Docling convert; return ``(result, error)``.

    ``raises_on_error=False`` lets Docling return PARTIAL_SUCCESS instead of
    re-raising page-batch OOMs. Native crashes still raise and become
    ``(None, exc)`` here (except cancel/skip, which propagate). Pass an existing
    ``converter`` to avoid reloading models between page batches.
    """
    built = converter or _build_converter(config, backend=backend)
    kwargs: dict[str, Any] = {"source": source_path, "raises_on_error": False}
    if page_range is not None:
        kwargs["page_range"] = page_range
    try:
        return built.convert(**kwargs), None
    except Exception as exc:  # noqa: BLE001 - catch native/process crashes from Docling
        if _is_cancellation(exc):
            raise
        _log_convert_failure(backend, page_range, exc)
        return None, exc
