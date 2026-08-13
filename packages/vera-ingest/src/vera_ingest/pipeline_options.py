"""Base class for plugin ``Options`` dataclasses.

Most pipeline settings are one of a handful of shapes: a boolean flag, an
integer with advertised bounds, a string restricted to a fixed set of choices,
or free text. :class:`PipelineOptions` validates a raw ``pipeline_options``
mapping against exactly those shapes, inferred from each dataclass field's
default value and ``metadata`` — the same ``metadata`` already used by
:func:`vera_ingest.descriptors.fields_from_dataclass` to build the CLI/GUI
descriptor — so a plugin whose settings all fit those shapes needs no
validation code at all.

A pipeline needing something beyond bool/int/choice/string validation (type
conversion, cross-field checks, normalizing a value) can still subclass
:class:`PipelineOptions` and override ``from_mapping`` itself; there is
nothing else in ``vera-ingest`` that requires this base class.
"""

from __future__ import annotations

from typing import ClassVar

from vera.core.option_parsing import OptionsBase


class PipelineOptions(OptionsBase):
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
    - an ``int`` default uses :func:`~vera_ingest.option_parsing.require_bounded_int`
      with ``metadata["minimum"]`` / ``metadata["maximum"]`` when those are
      numbers (otherwise the value must be non-negative);
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

    options_mapping_label: ClassVar[str] = "pipeline_options"
