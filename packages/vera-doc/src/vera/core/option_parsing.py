"""Helpers for strict plugin-owned option parsing.

:class:`OptionsBase.from_mapping` and :func:`fields_from_dataclass` are the
shared implementations used by ingest and embedding Options/descriptor
wrappers. Public plugin imports stay on those wrappers.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields
from typing import Any, ClassVar, TypeVar


def allowed_keys_from_dataclass(cls: type) -> set[str]:
    """Return a dataclass's field names as the allowed option keys.

    Keeps an Options dataclass the single source of truth for which keys
    ``from_mapping`` accepts, instead of a hand-maintained set kept in sync
    with the field list by hand.
    """
    return {item.name for item in fields(cls)}


def require_mapping(raw: Mapping[str, Any] | None, *, label: str) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise TypeError(f"{label} must be a mapping of string keys")
    return {str(key): value for key, value in raw.items()}


def reject_unknown_keys(
    raw: Mapping[str, Any],
    *,
    allowed: set[str],
    ignored: set[str] | None = None,
    label: str,
) -> dict[str, Any]:
    """Return only allowed keys; reject unknown non-ignored keys."""
    ignored_keys = ignored or set()
    unknown = sorted(key for key in raw if key not in allowed and key not in ignored_keys)
    if unknown:
        names = ", ".join(repr(key) for key in unknown)
        raise ValueError(f"Unknown {label} option(s): {names}")
    return {key: raw[key] for key in allowed if key in raw}


def require_positive_int(value: Any, *, name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be positive")
    return parsed


def require_non_negative_int(value: Any, *, name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed < 0:
        raise ValueError(f"{name} must be non-negative")
    return parsed


def _numeric_bound(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def require_bounded_int(
    value: Any,
    *,
    name: str,
    minimum: Any = None,
    maximum: Any = None,
) -> int:
    """Parse an integer and enforce advertised ``minimum`` / ``maximum`` bounds.

    When neither bound is a number, values must still be non-negative — the
    same floor ``from_mapping`` used before metadata ranges were enforced.
    """
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    lo = _numeric_bound(minimum)
    hi = _numeric_bound(maximum)
    if lo is not None and hi is not None:
        if parsed < lo or parsed > hi:
            raise ValueError(f"{name} must be between {lo} and {hi}")
    elif lo is not None:
        if parsed < lo:
            if lo == 0:
                raise ValueError(f"{name} must be non-negative")
            raise ValueError(f"{name} must be at least {lo}")
    elif hi is not None:
        if parsed < 0 or parsed > hi:
            raise ValueError(f"{name} must be between 0 and {hi}")
    elif parsed < 0:
        raise ValueError(f"{name} must be non-negative")
    return parsed


def require_string(value: Any, *, name: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    text = value.strip()
    if not allow_empty and not text:
        raise ValueError(f"{name} must not be empty")
    return text


def require_bool(value: Any, *, name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y", "on"}:
            return True
        if lowered in {"false", "0", "no", "n", "off", ""}:
            return False
    raise ValueError(f"{name} must be a boolean")


def require_choice(value: Any, *, name: str, choices: set[str]) -> str:
    text = require_string(value, name=name)
    normalized = text.lower()
    if normalized not in choices:
        allowed = ", ".join(sorted(choices))
        raise ValueError(f"Unsupported {name} {value!r}; use one of: {allowed}")
    return normalized


class OptionsBase:
    """Shared ``from_mapping`` for plugin ``Options`` dataclasses.

    Subclass alongside ``@dataclass(frozen=True)``. Field defaults and
    ``metadata`` pick the validator: ``bool``, bounded ``int``,
    ``choices``-restricted ``str``, or free-text ``str``. Override
    ``from_mapping`` when a field needs something those shapes cannot
    express.

    ``options_mapping_label`` is the noun used in ``require_mapping``
    errors (``"pipeline_options"`` / ``"embedder_options"``).
    """

    options_label: ClassVar[str] = ""
    ignored_keys: ClassVar[frozenset[str]] = frozenset()
    options_mapping_label: ClassVar[str] = "options"

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None = None) -> Any:
        label = cls.options_label or cls.__name__.removesuffix("Options") or cls.__name__
        data = reject_unknown_keys(
            require_mapping(raw, label=f"{label} {cls.options_mapping_label}"),
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


_FIELD_TYPE_BY_ANNOTATION = {
    "bool": "boolean",
    "int": "integer",
    "float": "number",
    "str": "string",
}

TField = TypeVar("TField")


def fields_from_dataclass(
    cls: type,
    *,
    field_cls: type[TField],
    choice_cls: type,
    include_scope: bool = False,
    include_allow_empty: bool = False,
) -> tuple[TField, ...]:
    """Derive descriptor fields from a dataclass's fields and per-field ``metadata``.

    ``field_cls`` / ``choice_cls`` are the public descriptor types to
    construct (``PipelineField`` or ``EmbedderField`` and their choice
    types). Embedder extras ``scope`` and ``allow_empty`` are copied from
    metadata only when the matching ``include_*`` flag is true — pipeline
    field types do not have those attributes.
    """
    result: list[TField] = []
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
            choice_cls(value, label) for value, label in meta.get("choices", ())
        )
        kwargs: dict[str, Any] = {
            "key": item.name,
            "label": meta.get("label", item.name),
            "type": field_type,
            "default": item.default,
            "description": meta.get("description", ""),
            "unit": meta.get("unit"),
            "choices": choices,
            "minimum": meta.get("minimum"),
            "maximum": meta.get("maximum"),
            "step": meta.get("step"),
            "placeholder": meta.get("placeholder"),
            "allow_custom": meta.get("allow_custom", False),
        }
        if include_allow_empty:
            kwargs["allow_empty"] = meta.get("allow_empty", False)
        if include_scope:
            scope = meta.get("scope", "convert")
            if scope not in {"convert", "always"}:
                raise ValueError(
                    f"Unsupported EmbedderField scope {scope!r} for {item.name}; "
                    "use 'convert' or 'always'"
                )
            kwargs["scope"] = scope
        result.append(field_cls(**kwargs))
    return tuple(result)
