"""Plugin-neutral ingest pipeline descriptors for discovery and GUI forms."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any, Literal


FieldType = Literal["string", "enum", "integer", "number", "boolean"]


@dataclass(frozen=True)
class PipelineFieldChoice:
    """One selectable value for an enum descriptor field."""

    value: str
    label: str


@dataclass(frozen=True)
class PipelineField:
    """Constrained configuration field advertised by a pipeline plugin."""

    key: str
    label: str
    type: FieldType
    default: Any = None
    description: str = ""
    unit: str | None = None
    choices: tuple[PipelineFieldChoice, ...] = ()
    minimum: int | float | None = None
    maximum: int | float | None = None
    step: int | float | None = None
    placeholder: str | None = None
    # When True on an enum field, GUIs may offer a free-text "Custom" value
    # (for example Tesseract ``eng+spa``) outside the advertised choices.
    allow_custom: bool = False


@dataclass(frozen=True)
class PipelineCapabilities:
    """Capability flags that help clients hide irrelevant controls."""

    chunk_unit: Literal["characters", "tokens", "words"] = "characters"
    overlap_supported: bool = True
    ocr_supported: bool = True
    ocr_engine: str | None = None
    ocr_dpi_supported: bool = True
    store_original_supported: bool = True
    source_formats: tuple[str, ...] = ("pdf",)


@dataclass(frozen=True)
class PipelineDescriptor:
    """Metadata describing an installed ingest pipeline provider/variant."""

    provider: str
    variant: str
    spec: str
    label: str
    description: str = ""
    installed: bool = True
    capabilities: PipelineCapabilities = field(default_factory=PipelineCapabilities)
    fields: tuple[PipelineField, ...] = ()
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


def fields_from_dataclass(cls: type) -> tuple[PipelineField, ...]:
    """Derive descriptor fields from a dataclass's fields and per-field ``metadata``.

    A plugin's ``Options`` dataclass stays the single source of truth for a
    setting's key and default: this reads them straight off each
    :func:`dataclasses.field`, and reads presentation data (``label``,
    ``description``, bounds, ``choices``, ...) from that field's ``metadata``
    mapping instead of a hand-maintained, parallel list of ``PipelineField``
    entries. A field with no ``metadata`` is treated as internal and omitted.

    ``metadata["type"]`` overrides the ``FieldType`` inferred from the
    field's annotation (used for ``"enum"`` fields, which are plain ``str``
    at the type level). ``metadata["choices"]`` is a sequence of
    ``(value, label)`` pairs.
    """
    result: list[PipelineField] = []
    for item in fields(cls):
        meta = item.metadata
        if not meta:
            continue
        # ``item.type`` is the annotation as written: a string when the
        # defining module uses ``from __future__ import annotations``
        # (postponed evaluation), otherwise the real type object.
        annotation = item.type
        type_name = annotation if isinstance(annotation, str) else getattr(
            annotation, "__name__", str(annotation)
        )
        field_type = meta.get("type") or _FIELD_TYPE_BY_ANNOTATION.get(type_name, "string")
        choices = tuple(
            PipelineFieldChoice(value, label) for value, label in meta.get("choices", ())
        )
        result.append(
            PipelineField(
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
            )
        )
    return tuple(result)


def generic_pipeline_descriptor(provider: str, variant: str = "") -> PipelineDescriptor:
    """Minimal fallback when a plugin does not register a descriptor."""
    spec = provider if not variant else f"{provider}:{variant}"
    label = provider if not variant else f"{provider} ({variant})"
    return PipelineDescriptor(
        provider=provider,
        variant=variant,
        spec=spec,
        label=label,
        description=f"Installed ingest pipeline '{spec}'.",
        notes=(
            "This plugin did not publish a configuration descriptor; "
            "use provider-documented pipeline options.",
        ),
    )
