"""Base class for embedding-provider ``Options`` dataclasses.

Most embedder settings are one of a handful of shapes: a boolean flag, an
integer with advertised bounds, a string restricted to a fixed set of choices,
or free text. :class:`EmbedderOptions` validates a raw options mapping against
exactly those shapes, inferred from each dataclass field's default value and
``metadata`` — the same ``metadata`` already used by
:func:`vera.core.embedder_descriptors.fields_from_dataclass` to build the
CLI/GUI descriptor — so a plugin whose settings all fit those shapes needs no
validation code at all.

A provider needing something beyond bool/int/choice/string validation can
still subclass :class:`EmbedderOptions` and override ``from_mapping``.
"""

from __future__ import annotations

from dataclasses import fields
from typing import Any, ClassVar, Mapping

from .option_parsing import (
    allowed_keys_from_dataclass,
    reject_unknown_keys,
    require_bool,
    require_bounded_int,
    require_choice,
    require_mapping,
    require_string,
)


class EmbedderOptions:
    """Base for an embedding provider's typed, validated settings.

    Subclass alongside ``@dataclass(frozen=True)``::

        @dataclass(frozen=True)
        class MyOptions(EmbedderOptions):
            batch_size: int = field(default=64, metadata={"label": "Batch size"})

    ``MyOptions.from_mapping(raw)`` validates a raw options dict field by
    field. For each field, its own default value's type picks the validator:

    - a ``bool`` default uses :func:`~vera.core.option_parsing.require_bool`;
    - an ``int`` default uses :func:`~vera.core.option_parsing.require_bounded_int`
      with ``metadata["minimum"]`` / ``metadata["maximum"]`` when those are
      numbers (otherwise the value must be non-negative);
    - a ``str`` default with ``metadata["choices"]`` and no
      ``metadata["allow_custom"]`` uses
      :func:`~vera.core.option_parsing.require_choice`;
    - any other ``str`` default uses :func:`~vera.core.option_parsing.require_string`
      (``metadata["allow_empty"]`` permits blank values).

    Two class attributes customize behavior without an override:

    - ``options_label`` sets the name used in error messages (default: the
      class name with a trailing ``Options`` dropped).
    - ``ignored_keys`` names legacy option keys to silently accept and drop.
    """

    options_label: ClassVar[str] = ""
    ignored_keys: ClassVar[frozenset[str]] = frozenset()

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None = None) -> Any:
        label = cls.options_label or cls.__name__.removesuffix("Options") or cls.__name__
        data = reject_unknown_keys(
            require_mapping(raw, label=f"{label} embedder_options"),
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
                values[name] = require_bounded_int(
                    value,
                    name=name,
                    minimum=item.metadata.get("minimum"),
                    maximum=item.metadata.get("maximum"),
                )
            else:
                choices = item.metadata.get("choices")
                if choices and not item.metadata.get("allow_custom"):
                    values[name] = require_choice(
                        value, name=name, choices={choice[0] for choice in choices}
                    )
                else:
                    values[name] = require_string(
                        value,
                        name=name,
                        allow_empty=bool(item.metadata.get("allow_empty")),
                    )
        return cls(**values)
