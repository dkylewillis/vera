"""Convert, ingest-pipeline, embedder, and OCR sidecar handlers."""

from __future__ import annotations

from typing import Any

from vera_app.cancellation import CancellationToken
from vera_app.types import Request, WriteEvent
from vera_doc import (
    list_embedding_models,
    list_embedding_provider_descriptors,
    list_embedding_providers,
    preflight_embedder,
)
from vera_ingest import (
    batch_convert,
    convert,
    list_ingest_pipeline_descriptors,
    list_ingest_pipelines,
)
from vera_ingest_pymupdf import (
    describe_ocr_languages,
    download_ocr_language_data,
)

_CONVERT_ALIAS_CASTERS = (
    ("chunk_size", int),
    ("overlap", int),
    ("ocr_mode", str),
    ("ocr_language", str),
    ("ocr_dpi", int),
    ("ocr_download", bool),
)


def explicit_convert_aliases(request: Request) -> dict[str, Any]:
    """Forward convert compatibility aliases only when the request set them."""
    return {key: caster(request[key]) for key, caster in _CONVERT_ALIAS_CASTERS if key in request}


def require_ready_embedder(model: str) -> None:
    """Refuse conversion when the selected embedder cannot be resolved later."""
    result = preflight_embedder(model)
    if not result.ok:
        raise ValueError(result.detail or "Embedding provider is not ready")


# 0.3.x desktop Convert ships PyMuPDF only. The Docling plugin remains a CLI extra.
_DESKTOP_EXCLUDED_PIPELINE_PROVIDERS = frozenset({"docling"})


def _pipeline_provider(name: str) -> str:
    return str(name or "").strip().lower().split(":", 1)[0]


def _reject_excluded_desktop_parser(request: Request) -> None:
    parser = str(request.get("parser") or "pymupdf")
    if _pipeline_provider(parser) not in _DESKTOP_EXCLUDED_PIPELINE_PROVIDERS:
        return
    raise ValueError(
        "Docling is not available in the desktop app in 0.3.x. "
        "Convert PDFs with PyMuPDF here, or use the CLI extra: "
        'pip install "vera-cli[docling]>=0.3.0"'
    )


def handle_convert(
    request: Request,
    write_event: WriteEvent | None = None,
    cancel: CancellationToken | None = None,
) -> dict[str, str]:
    input_path = str(request["input"])
    _reject_excluded_desktop_parser(request)
    if write_event:
        write_event(
            {
                "event": "conversion_progress",
                "completed": 0,
                "total": 1,
                "input": input_path,
            }
        )
    raw_pipeline_options = request.get("pipeline_options")
    pipeline_options = (
        dict(raw_pipeline_options) if isinstance(raw_pipeline_options, dict) else None
    )
    raw_embedder_options = request.get("embedder_options")
    embedder_options = (
        dict(raw_embedder_options) if isinstance(raw_embedder_options, dict) else None
    )
    require_ready_embedder(str(request.get("model", "hashing")))
    output = convert(
        input_path,
        str(request["output"]),
        model=str(request.get("model", "hashing")),
        parser=str(request.get("parser", "pymupdf")),
        store_original=bool(request.get("store_original", True)),
        pipeline_options=pipeline_options,
        embedder_options=embedder_options,
        cancel=cancel,
        **explicit_convert_aliases(request),
    )
    if write_event:
        write_event(
            {
                "event": "conversion_progress",
                "completed": 1,
                "total": 1,
                "input": input_path,
            }
        )
    return {"output": output}


def handle_batch_convert(
    request: Request,
    write_event: WriteEvent | None = None,
    cancel: CancellationToken | None = None,
) -> dict[str, Any]:
    def report_progress(completed: int, total: int, input_path: str) -> None:
        if cancel:
            cancel.raise_if_interrupted()
        if write_event:
            write_event(
                {
                    "event": "conversion_progress",
                    "completed": completed,
                    "total": total,
                    "input": input_path,
                }
            )

    raw_paths = request.get("paths")
    paths: list[str] | None = None
    if isinstance(raw_paths, list):
        paths = [str(item) for item in raw_paths if str(item).strip()]
        if not paths:
            paths = None

    directory = request.get("directory")
    progress_label = (
        f"{len(paths)} selected PDF{'s' if len(paths) != 1 else ''}"
        if paths is not None
        else str(directory or "")
    )
    if write_event:
        write_event(
            {
                "event": "conversion_progress",
                "completed": 0,
                "total": 0,
                "input": progress_label,
                "phase": "discovering",
            }
        )
    if cancel:
        cancel.raise_if_interrupted()
    _reject_excluded_desktop_parser(request)
    require_ready_embedder(str(request.get("model", "hashing")))

    return batch_convert(
        None if paths is not None else str(directory),
        paths=paths,
        recursive=bool(request.get("recursive", True)),
        overwrite=bool(request.get("overwrite", False)),
        model=str(request.get("model", "hashing")),
        parser=str(request.get("parser", "pymupdf")),
        store_original=bool(request.get("store_original", True)),
        pipeline_options=(
            dict(request["pipeline_options"])
            if isinstance(request.get("pipeline_options"), dict)
            else None
        ),
        embedder_options=(
            dict(request["embedder_options"])
            if isinstance(request.get("embedder_options"), dict)
            else None
        ),
        progress=report_progress,
        cancel=cancel,
        **explicit_convert_aliases(request),
    )


def handle_list_embedding_providers(request: Request) -> dict[str, Any]:
    """List registered embedding providers for the conversion settings UI."""
    return {"providers": list_embedding_providers()}


def handle_describe_embedding_providers(request: Request) -> dict[str, Any]:
    """Return installed embedding-provider descriptors for schema-driven controls."""
    return {
        "providers": [descriptor.as_dict() for descriptor in list_embedding_provider_descriptors()],
    }


def handle_list_embedding_models(request: Request) -> dict[str, Any]:
    """Return model ids advertised by one embedding provider."""
    provider = str(request.get("provider") or "").strip()
    if not provider:
        raise ValueError("provider is required")
    return {
        "provider": provider,
        "models": [item.as_dict() for item in list_embedding_models(provider)],
    }


def handle_preflight_embedder(request: Request) -> dict[str, Any]:
    """Check credential/env readiness for a model spec without loading runtimes."""
    model = str(request.get("model") or "hashing")
    return preflight_embedder(model).as_dict()


def handle_list_ingest_pipelines(request: Request) -> dict[str, Any]:
    """List installed ingest pipeline providers for the Convert view."""
    return {
        "pipelines": [
            name
            for name in list_ingest_pipelines()
            if _pipeline_provider(name) not in _DESKTOP_EXCLUDED_PIPELINE_PROVIDERS
        ]
    }


def handle_describe_ingest_pipelines(request: Request) -> dict[str, Any]:
    """Return installed pipeline descriptors for schema-driven Convert controls."""
    return {
        "pipelines": [
            descriptor.as_dict()
            for descriptor in list_ingest_pipeline_descriptors()
            if descriptor.provider not in _DESKTOP_EXCLUDED_PIPELINE_PROVIDERS
        ],
    }


def handle_ocr_languages_list(request: Request) -> dict[str, Any]:
    """Report bundled/cached/downloadable status for Tesseract OCR language codes."""
    language = request.get("language")
    return {"languages": describe_ocr_languages(str(language) if language else None)}


def handle_ocr_languages_download(
    request: Request,
    write_event: WriteEvent | None = None,
    cancel: CancellationToken | None = None,
) -> dict[str, Any]:
    """Fetch (or reuse cached) Tesseract language data, streaming download progress."""
    language = str(request.get("language") or "").strip()
    if not language:
        raise ValueError("language is required")

    def report_progress(code: str, downloaded: int, total: int) -> None:
        if cancel:
            cancel.raise_if_interrupted()
        if write_event:
            write_event(
                {
                    "event": "ocr_download_progress",
                    "language": code,
                    "downloaded": downloaded,
                    "total": total,
                }
            )

    cache_dir = download_ocr_language_data(language, progress=report_progress)
    codes = [part.strip() for part in language.split("+") if part.strip()]
    return {"language": language, "downloaded": codes, "cache_dir": cache_dir}
