"""Plugin-neutral embedding-provider descriptors for discovery and GUI forms."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .option_parsing import fields_from_dataclass as _fields_from_dataclass


FieldType = Literal["string", "enum", "integer", "number", "boolean"]
FieldScope = Literal["convert", "always"]


@dataclass(frozen=True)
class EmbedderFieldChoice:
    """One selectable value for an enum descriptor field."""

    value: str
    label: str


@dataclass(frozen=True)
class EmbedderField:
    """Constrained configuration field advertised by an embedding provider."""

    key: str
    label: str
    type: FieldType
    default: Any = None
    description: str = ""
    unit: str | None = None
    choices: tuple[EmbedderFieldChoice, ...] = ()
    minimum: int | float | None = None
    maximum: int | float | None = None
    step: int | float | None = None
    placeholder: str | None = None
    # When True on an enum field, GUIs may offer a free-text "Custom" value
    # outside the advertised choices.
    allow_custom: bool = False
    # When True on a string field, blank values are valid (for example an
    # optional device string that means "auto").
    allow_empty: bool = False
    # ``convert`` options affect embedding throughput/hardware only and may use
    # defaults at search time. ``always`` options participate in archive
    # identity (for example hashing dimension) and must round-trip via
    # ``model_name`` or explicit search-time config.
    scope: FieldScope = "convert"


@dataclass(frozen=True)
class EmbedderCapabilities:
    """Capability flags that help clients hide irrelevant controls."""

    requires_network: bool = False
    requires_api_key: bool = False
    # Environment variable the provider reads for credentials (never put secrets
    # in Options fields or descriptors). Empty when no API key is required.
    credential_env: str = ""
    local_model: bool = True
    configurable_dimension: bool = False
    # When True, ``list_embedding_models(provider)`` is expected to return
    # useful model ids (static presets and/or a live provider listing).
    supports_model_listing: bool = False


@dataclass(frozen=True)
class EmbeddingModelInfo:
    """One selectable model id advertised by an embedding provider."""

    model_id: str
    label: str = ""
    spec: str = ""
    description: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EmbedderPreflightResult:
    """Lightweight readiness check for an embedding provider or model spec."""

    ok: bool
    provider: str
    model_id: str = ""
    missing_credential_env: str = ""
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EmbedderDescriptor:
    """Metadata describing an installed embedding provider."""

    provider: str
    label: str
    description: str = ""
    installed: bool = True
    default_model_id: str = ""
    example_specs: tuple[str, ...] = ()
    capabilities: EmbedderCapabilities = field(default_factory=EmbedderCapabilities)
    fields: tuple[EmbedderField, ...] = ()
    notes: tuple[str, ...] = ()

    def field_keys(self) -> set[str]:
        return {item.key for item in self.fields}

    def defaults(self) -> dict[str, Any]:
        return {item.key: item.default for item in self.fields}

    def convert_fields(self) -> tuple[EmbedderField, ...]:
        """Fields that are convert-time only (safe to default at search)."""
        return tuple(item for item in self.fields if item.scope == "convert")

    def always_fields(self) -> tuple[EmbedderField, ...]:
        """Fields that participate in archive identity / search resolve."""
        return tuple(item for item in self.fields if item.scope == "always")

    def as_dict(self) -> dict[str, Any]:
        """Serialize for sidecar/CLI JSON clients."""
        return asdict(self)


def fields_from_dataclass(cls: type) -> tuple[EmbedderField, ...]:
    """Derive descriptor fields from a dataclass's fields and per-field ``metadata``.

    A provider's ``Options`` dataclass stays the single source of truth for a
    setting's key and default: this reads them straight off each
    :func:`dataclasses.field`, and reads presentation data (``label``,
    ``description``, bounds, ``choices``, ...) from that field's ``metadata``
    mapping instead of a hand-maintained, parallel list of ``EmbedderField``
    entries. A field with no ``metadata`` is treated as internal and omitted.
    """
    return _fields_from_dataclass(
        cls,
        field_cls=EmbedderField,
        choice_cls=EmbedderFieldChoice,
        include_scope=True,
        include_allow_empty=True,
    )


def generic_embedder_descriptor(provider: str) -> EmbedderDescriptor:
    """Minimal fallback when a plugin does not register a descriptor."""
    return EmbedderDescriptor(
        provider=provider,
        label=provider,
        description=f"Installed embedding provider '{provider}'.",
        notes=(
            "This plugin did not publish a configuration descriptor; "
            "use provider-documented embedder options.",
        ),
    )
