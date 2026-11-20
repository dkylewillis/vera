"""Plugin-neutral ingest pipeline descriptors for discovery and GUI forms."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from dataclasses import fields as dataclass_fields
from typing import Any, Literal

from vera_doc.option_parsing import fields_from_dataclass as _fields_from_dataclass

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
    requires_api_key: bool = False
    credential_env: str = ""


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
    # Other variants this provider accepts as ``provider:variant``. Set on the
    # default variant's descriptor so clients can list them.
    variants: tuple[str, ...] = ()

    def field_keys(self) -> set[str]:
        return {item.key for item in self.fields}

    def defaults(self) -> dict[str, Any]:
        return {item.key: item.default for item in self.fields}

    def as_dict(self) -> dict[str, Any]:
        """Serialize for sidecar/CLI JSON clients."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PipelineDescriptor:
        """Rebuild a descriptor from :meth:`as_dict` output.

        Keys this version does not know are ignored, so a descriptor written
        by a newer ``vera-ingest`` in another environment still loads.
        """
        provider = str(data.get("provider") or "").strip().lower()
        if not provider:
            raise ValueError("pipeline descriptor has no provider")
        variant = str(data.get("variant") or "").strip().lower()
        capabilities = _known(PipelineCapabilities, data.get("capabilities"))
        if "source_formats" in capabilities:
            capabilities["source_formats"] = tuple(
                str(item).strip().lower().lstrip(".") for item in capabilities["source_formats"]
            )
        pipeline_fields = []
        for raw in data.get("fields") or ():
            values = _known(PipelineField, raw)
            values["choices"] = tuple(
                PipelineFieldChoice(**_known(PipelineFieldChoice, choice))
                for choice in values.get("choices") or ()
            )
            pipeline_fields.append(PipelineField(**values))
        return cls(
            provider=provider,
            variant=variant,
            spec=str(data.get("spec") or (f"{provider}:{variant}" if variant else provider)),
            label=str(data.get("label") or provider),
            description=str(data.get("description") or ""),
            installed=bool(data.get("installed", True)),
            capabilities=PipelineCapabilities(**capabilities),
            fields=tuple(pipeline_fields),
            notes=tuple(str(item) for item in data.get("notes") or ()),
            variants=tuple(str(item) for item in data.get("variants") or ()),
        )


def _known(cls: type, data: Any) -> dict[str, Any]:
    """Keep only the keys ``cls`` declares as dataclass fields."""
    if not isinstance(data, Mapping):
        return {}
    names = {item.name for item in dataclass_fields(cls)}
    return {key: value for key, value in data.items() if key in names}


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
    return _fields_from_dataclass(cls, field_cls=PipelineField, choice_cls=PipelineFieldChoice)


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
