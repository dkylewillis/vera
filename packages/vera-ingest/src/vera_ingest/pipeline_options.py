"""Optional convenience base for plugin ``Options`` dataclasses.

Most pipeline settings are one of a handful of shapes: a boolean flag, an
integer with a floor, a string restricted to a fixed set of choices, or free
text. :func:`coerce_pipeline_options` validates a raw ``pipeline_options``
mapping against exactly those shapes, inferred from each dataclass field's
default value and ``metadata`` — the same ``metadata`` already used by
:func:`vera_ingest.descriptors.fields_from_dataclass` to build the CLI/GUI
descriptor. :class:`PipelineOptions` wraps that as an inherited
``from_mapping`` so a straightforward plugin needs no validation code at all.

This is convenience, not a requirement. A pipeline whose settings need
anything beyond bool/int/choice/string validation — type conversion, cross-
field checks, or normalizing a value (see ``vera-ingest-docling``'s
``ocr_language``, which remaps Tesseract-style codes to RapidOCR's) should
either skip :class:`PipelineOptions` and write ``from_mapping`` directly with
the :mod:`vera_ingest.option_parsing` helpers, or call
:func:`coerce_pipeline_options` for the mechanical part and adjust its result
before constructing the instance — see the docstring example below.
"""

from __future__ import annotations

from dataclasses import fields
from typing import Any, Mapping

from .option_parsing import (
    allowed_keys_from_dataclass,
    reject_unknown_keys,
    require_bool,
    require_choice,
    require_mapping,
    require_non_negative_int,
    require_positive_int,
    require_string,
)


def coerce_pipeline_options(
    cls: type,
    raw: Mapping[str, Any] | None,
    *,
    label: str,
    ignored: set[str] | None = None,
) -> dict[str, Any]:
    """Validate ``raw`` against ``cls``'s dataclass fields, by field shape.

    For each field, ``cls``'s own default value (not the field's static
    annotation, which may be a string under ``from __future__ import
    annotations``) decides how it's validated:

    - a ``bool`` default uses :func:`require_bool`;
    - an ``int`` default uses :func:`require_positive_int` when
      ``metadata["minimum"]`` is a positive number, otherwise
      :func:`require_non_negative_int`;
    - a ``str`` default with ``metadata["choices"]`` and no
      ``metadata["allow_custom"]`` uses :func:`require_choice` restricted to
      those choices' values;
    - any other ``str`` default uses :func:`require_string` (free text —
      this is also what a ``choices`` field with ``allow_custom: True``
      uses, since a GUI-only choice list should not reject custom values).

    A field of any other type (for example ``float``) is not supported by
    this helper; write ``from_mapping`` for it directly instead.

    Returns a plain ``dict`` of validated field values, keyed by field name,
    suitable for ``cls(**result)``. Raises :class:`ValueError` naming the
    offending key for an unknown ``pipeline_options`` key or an invalid
    value, exactly as calling the individual ``option_parsing`` helpers by
    hand would.
    """
    data = reject_unknown_keys(
        require_mapping(raw, label=f"{label} pipeline_options"),
        allowed=allowed_keys_from_dataclass(cls),
        ignored=ignored,
        label=label,
    )
    coerced: dict[str, Any] = {}
    for item in fields(cls):
        name = item.name
        default = getattr(cls, name)
        value = data.get(name, default)
        if isinstance(default, bool):
            coerced[name] = require_bool(value, name=name)
        elif isinstance(default, int):
            minimum = item.metadata.get("minimum")
            if isinstance(minimum, (int, float)) and minimum > 0:
                coerced[name] = require_positive_int(value, name=name)
            else:
                coerced[name] = require_non_negative_int(value, name=name)
        else:
            choices = item.metadata.get("choices")
            if choices and not item.metadata.get("allow_custom"):
                coerced[name] = require_choice(
                    value, name=name, choices={choice[0] for choice in choices}
                )
            else:
                coerced[name] = require_string(value, name=name)
    return coerced


class PipelineOptions:
    """Mixin adding ``from_mapping`` for dataclasses of bool/int/choice/string fields.

    Subclass alongside ``@dataclass(frozen=True)``::

        @dataclass(frozen=True)
        class MyOptions(PipelineOptions):
            chunk_size: int = field(default=2000, metadata={"label": "Chunk size"})

    ``MyOptions.from_mapping(raw)`` is then generated for you — see
    :func:`coerce_pipeline_options` for exactly how each field is validated.
    The error-message label defaults to the class name with a trailing
    ``Options`` dropped (``MyOptions`` -> ``"MyOptions"`` has no such
    suffix here, so it stays ``MyOptions``; ``PyMuPDFOptions`` would become
    ``"PyMuPDF"``). Override :attr:`options_label` to set it explicitly.

    A pipeline needing custom coercion for one field can still call
    :func:`coerce_pipeline_options` directly instead of inheriting this
    mixin, adjust the one field it needs to, and construct the instance
    itself — see ``vera_ingest_docling.options.DoclingOptions`` for a real
    example (it remaps ``ocr_language`` after the mechanical validation).
    """

    options_label: str = ""

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None = None) -> Any:
        label = cls.options_label or cls.__name__.removesuffix("Options") or cls.__name__
        return cls(**coerce_pipeline_options(cls, raw, label=label))
