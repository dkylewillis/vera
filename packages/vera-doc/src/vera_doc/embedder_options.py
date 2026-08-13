"""Base class for embedding-provider ``Options`` dataclasses.

Most embedder settings are one of a handful of shapes: a boolean flag, an
integer with advertised bounds, a string restricted to a fixed set of choices,
or free text. :class:`EmbedderOptions` validates a raw options mapping against
exactly those shapes, inferred from each dataclass field's default value and
``metadata`` — the same ``metadata`` already used by
:func:`vera_doc.embedder_descriptors.fields_from_dataclass` to build the
CLI/GUI descriptor — so a plugin whose settings all fit those shapes needs no
validation code at all.

A provider needing something beyond bool/int/choice/string validation can
still subclass :class:`EmbedderOptions` and override ``from_mapping``.
"""

from __future__ import annotations

from typing import ClassVar

from .option_parsing import OptionsBase


class EmbedderOptions(OptionsBase):
    """Base for an embedding provider's typed, validated settings.

    Subclass alongside ``@dataclass(frozen=True)``::

        @dataclass(frozen=True)
        class MyOptions(EmbedderOptions):
            batch_size: int = field(default=64, metadata={"label": "Batch size"})

    ``MyOptions.from_mapping(raw)`` validates a raw options dict field by
    field. For each field, its declared type and ``metadata`` pick the
    validator (not the default value's type):

    - a ``bool`` field uses :func:`~vera_doc.option_parsing.require_bool`;
    - an ``int`` field uses :func:`~vera_doc.option_parsing.require_bounded_int`
      with ``metadata["minimum"]`` / ``metadata["maximum"]`` / ``metadata["step"]``
      when those are numbers (``step`` is enforced for embedder options;
      otherwise the value must be non-negative);
    - a ``str`` field with ``metadata["choices"]`` and no
      ``metadata["allow_custom"]`` uses
      :func:`~vera_doc.option_parsing.require_choice`;
    - any other ``str`` field uses :func:`~vera_doc.option_parsing.require_string`
      (``metadata["allow_empty"]`` permits blank values).

    Two class attributes customize behavior without an override:

    - ``options_label`` sets the name used in error messages (default: the
      class name with a trailing ``Options`` dropped).
    - ``ignored_keys`` names legacy option keys to silently accept and drop.
    """

    options_mapping_label: ClassVar[str] = "embedder_options"
    enforce_step: ClassVar[bool] = True
