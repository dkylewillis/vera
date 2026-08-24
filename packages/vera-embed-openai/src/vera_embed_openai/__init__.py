"""Official OpenAI embeddings provider for VERA."""

from __future__ import annotations

from vera_doc import (
    EmbedderDescriptor,
    EmbeddingModelInfo,
    register_embedder,
    register_embedder_descriptor,
    register_embedder_models,
)

from .options import (
    BASE_URL_ENV,
    CREDENTIAL_ENV,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL_ID,
    MODEL_DIMENSIONS,
    PROVIDER,
    OpenAIOptions,
    describe_provider,
)
from .options import list_models as _list_models
from .provider import (
    MAX_INPUT_TOKENS,
    MAX_REQUEST_TOKENS,
    OpenAIEmbedder,
    OpenAIEmbedderError,
    create_embedder,
    embeddings_url,
    estimate_tokens,
    iter_embed_batches,
)

__all__ = [
    "BASE_URL_ENV",
    "CREDENTIAL_ENV",
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL_ID",
    "MAX_INPUT_TOKENS",
    "MAX_REQUEST_TOKENS",
    "MODEL_DIMENSIONS",
    "OpenAIEmbedder",
    "OpenAIEmbedderError",
    "OpenAIOptions",
    "PROVIDER",
    "create_descriptor",
    "create_embedder",
    "describe_provider",
    "embeddings_url",
    "ensure_registered",
    "estimate_tokens",
    "iter_embed_batches",
    "list_models",
]


def create_descriptor() -> EmbedderDescriptor:
    """Entry-point factory for ``vera.embedder_descriptors``."""
    return describe_provider()


def list_models() -> tuple[EmbeddingModelInfo, ...]:
    """Entry-point factory for ``vera.embedder_models``."""
    return _list_models()


def ensure_registered(*, replace: bool = True) -> None:
    """Register the ``openai`` embedder without relying on package metadata.

    Entry-point discovery fails in PyInstaller freezes and PYTHONPATH-only
    source runs that never install ``vera-embed-openai`` dist-info. Callers
    that already import this package (CLI, the desktop sidecar) should invoke
    this so Convert and search still resolve the provider.
    """
    register_embedder(PROVIDER, create_embedder, replace=replace)
    register_embedder_descriptor(PROVIDER, create_descriptor, replace=replace)
    register_embedder_models(PROVIDER, list_models, replace=replace)


ensure_registered()
