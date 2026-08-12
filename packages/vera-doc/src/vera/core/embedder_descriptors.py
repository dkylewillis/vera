"""Plugin-neutral embedding-provider descriptors for discovery and GUI forms."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any, Literal


FieldType = Literal["string", "enum", "integer", "number", "boolean"]


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


@dataclass(frozen=True)
class EmbedderCapabilities:
    """Capability flags that help clients hide irrelevant controls."""

    requires_network: bool = False
    requires_api_key: bool = False
    local_model: bool = True
    configurable_dimension: bool = False


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

    def as_dict(self) -> dict[str, Any]:
        """Serialize for sidecar/CLI JSON clients."""
        return asdict(self)


_FIELD_TYPE_BY_ANNOTATION = {
    "bool": "boolean",
    "int": "integer",
    "float": "number",
    "str": "string",
}


def fields_from_dataclass(cls: type) -> tuple[EmbedderField, ...]:
    """Derive descriptor fields from a dataclass's fields and per-field ``metadata``.

    A provider's ``Options`` dataclass stays the single source of truth for a
    setting's key and default: this reads them straight off each
    :func:`dataclasses.field`, and reads presentation data (``label``,
    ``description``, bounds, ``choices``, ...) from that field's ``metadata``
    mapping instead of a hand-maintained, parallel list of ``EmbedderField``
    entries. A field with no ``metadata`` is treated as internal and omitted.
    """
    result: list[EmbedderField] = []
    for item in fields(cls):
        meta = item.metadata
        if not meta:
            continue
        annotation = item.type
        type_name = annotation if isinstance(annotation, str) else getattr(
            annotation, "__name__", str(annotation)
        )
        field_type = meta.get("type") or _FIELD_TYPE_BY_ANNOTATION.get(type_name, "string")
        choices = tuple(
            EmbedderFieldChoice(value, label) for value, label in meta.get("choices", ())
        )
        result.append(
            EmbedderField(
                key=item.name,
                label=meta.get("label", item.name),
                type=field_type,
                default=item.default,
                description=meta.get("description", ""),
                unit=meta.get("unit"),
                choices=choices,
                minimum=meta.get("minimum"),
                maximum=meta.get("maximum"),
                step=meta.get("step"),
                placeholder=meta.get("placeholder"),
                allow_custom=meta.get("allow_custom", False),
                allow_empty=meta.get("allow_empty", False),
            )
        )
    return tuple(result)


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
