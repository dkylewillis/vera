"""Helpers for strict plugin-owned option parsing.

Canonical implementation lives in :mod:`vera.core.option_parsing`. This module
re-exports those helpers so ingest pipelines and older imports keep working
without duplicating validators.
"""

from __future__ import annotations

from vera.core.option_parsing import (
    allowed_keys_from_dataclass,
    reject_unknown_keys,
    require_bool,
    require_choice,
    require_mapping,
    require_non_negative_int,
    require_positive_int,
    require_string,
)

__all__ = [
    "allowed_keys_from_dataclass",
    "reject_unknown_keys",
    "require_bool",
    "require_choice",
    "require_mapping",
    "require_non_negative_int",
    "require_positive_int",
    "require_string",
]
