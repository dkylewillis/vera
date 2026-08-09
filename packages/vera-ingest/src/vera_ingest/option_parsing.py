"""Helpers for strict plugin-owned option parsing."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


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


def require_string(value: Any, *, name: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    text = value.strip()
    if not allow_empty and not text:
        raise ValueError(f"{name} must not be empty")
    return text


def require_choice(value: Any, *, name: str, choices: set[str]) -> str:
    text = require_string(value, name=name)
    normalized = text.lower()
    if normalized not in choices:
        allowed = ", ".join(sorted(choices))
        raise ValueError(f"Unsupported {name} {value!r}; use one of: {allowed}")
    return normalized
