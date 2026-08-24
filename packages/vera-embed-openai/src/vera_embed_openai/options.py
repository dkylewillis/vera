"""Typed options, descriptor, and model list for the OpenAI embedder."""

from __future__ import annotations

from dataclasses import dataclass, field

from vera_doc import (
    EmbedderCapabilities,
    EmbedderDescriptor,
    EmbedderOptions,
    EmbeddingModelInfo,
)
from vera_doc.embedder_descriptors import fields_from_dataclass

PROVIDER = "openai"
DEFAULT_MODEL_ID = "text-embedding-3-small"
CREDENTIAL_ENV = "OPENAI_API_KEY"
BASE_URL_ENV = "OPENAI_BASE_URL"
DEFAULT_BASE_URL = "https://api.openai.com/v1"

MODEL_DIMENSIONS: dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


@dataclass(frozen=True)
class OpenAIOptions(EmbedderOptions):
    """OpenAI-owned convert-time embedding settings.

    Credentials and the API root stay in the environment
    (``OPENAI_API_KEY``, optional ``OPENAI_BASE_URL``), not in this dataclass.
    """

    batch_size: int = field(
        default=128,
        metadata={
            "label": "Batch size",
            "description": (
                "Maximum texts per OpenAI request. Requests also split when "
                "the estimated token budget would be exceeded. Convert-time "
                "only — search uses the default."
            ),
            "minimum": 1,
            "maximum": 2048,
            "step": 1,
            "scope": "convert",
        },
    )
    timeout: int = field(
        default=60,
        metadata={
            "label": "Timeout",
            "description": (
                "Seconds to wait for each embeddings HTTP response. "
                "Convert-time only — search uses the default."
            ),
            "unit": "seconds",
            "minimum": 1,
            "maximum": 600,
            "step": 1,
            "scope": "convert",
        },
    )


def describe_provider() -> EmbedderDescriptor:
    return EmbedderDescriptor(
        provider=PROVIDER,
        label="openai — hosted embeddings",
        description=(
            "OpenAI embeddings API (text-embedding-3-* and similar). "
            "Requires OPENAI_API_KEY. Archives converted with this provider "
            "need the same key for later semantic or hybrid search; keyword "
            "search still works offline. Conversion bills per request."
        ),
        default_model_id=DEFAULT_MODEL_ID,
        example_specs=(
            "openai:text-embedding-3-small",
            "openai:text-embedding-3-large",
        ),
        capabilities=EmbedderCapabilities(
            requires_network=True,
            requires_api_key=True,
            credential_env=CREDENTIAL_ENV,
            local_model=False,
            configurable_dimension=False,
            supports_model_listing=True,
        ),
        fields=fields_from_dataclass(OpenAIOptions),
        notes=(
            "Set OPENAI_API_KEY (desktop: File > Settings → Embeddings). "
            "Optional OPENAI_BASE_URL overrides the API root "
            f"(default {DEFAULT_BASE_URL}); archives still record "
            "openai:<model-id>, so a custom endpoint that serves a different "
            "model is not detectable at search time. "
            "batch_size and timeout are convert-time options; search uses defaults. "
            "Cancel does not interrupt an in-flight embeddings request.",
        ),
    )


def list_models() -> tuple[EmbeddingModelInfo, ...]:
    return (
        EmbeddingModelInfo(
            model_id="text-embedding-3-small",
            label="text-embedding-3-small",
            spec="openai:text-embedding-3-small",
            description="OpenAI text-embedding-3-small (1536-d).",
        ),
        EmbeddingModelInfo(
            model_id="text-embedding-3-large",
            label="text-embedding-3-large",
            spec="openai:text-embedding-3-large",
            description="OpenAI text-embedding-3-large (3072-d).",
        ),
        EmbeddingModelInfo(
            model_id="text-embedding-ada-002",
            label="text-embedding-ada-002",
            spec="openai:text-embedding-ada-002",
            description="Legacy OpenAI ada embedding model (1536-d).",
        ),
    )
