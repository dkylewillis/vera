"""Base class for plugin ``Options`` dataclasses.

Most pipeline settings are one of a handful of shapes: a boolean flag, an
integer with a floor, a string restricted to a fixed set of choices, or free
text. :class:`PipelineOptions` validates a raw ``pipeline_options`` mapping
against exactly those shapes, inferred from each dataclass field's default
value and ``metadata`` — the same ``metadata`` already used by
:func:`vera_ingest.descriptors.fields_from_dataclass` to build the CLI/GUI
descriptor — so a plugin whose settings all fit those shapes needs no
validation code at all.

A pipeline needing something beyond bool/int/choice/string validation (type
conversion, cross-field checks, normalizing a value) can still subclass
:class:`PipelineOptions` and override ``from_mapping`` itself; there is
nothing else in ``vera-ingest`` that requires this base class.
"""

from __future__ import annotations

from dataclasses import fields
from typing import Any, ClassVar, Mapping

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


class PipelineOptions:
    """Base for an ingest pipeline's typed, validated settings.

    Subclass alongside ``@dataclass(frozen=True)``::

        @dataclass(frozen=True)
        class MyOptions(PipelineOptions):
            chunk_size: int = field(default=2000, metadata={"label": "Chunk size"})

    ``MyOptions.from_mapping(raw)`` validates a raw ``pipeline_options`` dict
    field by field. For each field, its own default value's type (not its
    static annotation, which may be a string under ``from __future__ import
    annotations``) picks the validator:

    - a ``bool`` default uses :func:`~vera_ingest.option_parsing.require_bool`;
    - an ``int`` default uses :func:`~vera_ingest.option_parsing.require_positive_int`
      when ``metadata["minimum"]`` is a positive number, otherwise
      :func:`~vera_ingest.option_parsing.require_non_negative_int`;
    - a ``str`` default with ``metadata["choices"]`` and no
      ``metadata["allow_custom"]`` uses
      :func:`~vera_ingest.option_parsing.require_choice` restricted to those
      choices' values;
    - any other ``str`` default uses :func:`~vera_ingest.option_parsing.require_string`
      (free text).

    A field of any other type (for example ``float``) is not supported;
    override ``from_mapping`` for a class with such a field instead.

    Two class attributes customize behavior without any of that:

    - ``options_label`` sets the name used in error messages (default: the
      class name with a trailing ``Options`` dropped, so ``PyMuPDFOptions``
      reads as ``"PyMuPDF"``).
    - ``ignored_keys`` names legacy ``pipeline_options`` keys to silently
      accept and drop instead of rejecting as unknown — for compatibility
      aliases shared with another pipeline that don't apply to this one.
    """

    options_label: ClassVar[str] = ""
    ignored_keys: ClassVar[frozenset[str]] = frozenset()

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None = None) -> Any:
        label = cls.options_label or cls.__name__.removesuffix("Options") or cls.__name__
        data = reject_unknown_keys(
            require_mapping(raw, label=f"{label} pipeline_options"),
            allowed=allowed_keys_from_dataclass(cls),
            ignored=cls.ignored_keys or None,
            label=label,
        )
        values: dict[str, Any] = {}
        for item in fields(cls):
            name = item.name
            default = getattr(cls, name)
            value = data.get(name, default)
            if isinstance(default, bool):
                values[name] = require_bool(value, name=name)
            elif isinstance(default, int):
                minimum = item.metadata.get("minimum")
                if isinstance(minimum, (int, float)) and minimum > 0:
                    values[name] = require_positive_int(value, name=name)
                else:
                    values[name] = require_non_negative_int(value, name=name)
            else:
                choices = item.metadata.get("choices")
                if choices and not item.metadata.get("allow_custom"):
                    values[name] = require_choice(
                        value, name=name, choices={choice[0] for choice in choices}
                    )
                else:
                    values[name] = require_string(value, name=name)
        return cls(**values)
