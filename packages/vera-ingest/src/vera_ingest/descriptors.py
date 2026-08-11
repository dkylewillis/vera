"""Plugin-neutral ingest pipeline descriptors for discovery and GUI forms."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
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

    chunk_unit: Literal["characters", "tokens"] = "characters"
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
