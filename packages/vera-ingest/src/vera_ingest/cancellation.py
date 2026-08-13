"""Cooperative cancel/interrupt checks shared by convert and ingest pipelines."""

from __future__ import annotations

from typing import Any


def raise_if_cancelled(cancel: Any | None) -> None:
    """Raise when an optional cancel token requested interrupt or cancel.

    Tokens may implement ``raise_if_interrupted`` (sidecar: cancel or skip)
    and/or ``raise_if_cancelled`` (cancel only). Interrupt is preferred when
    both exist so skip requests surface during ingest work.
    """
    if cancel is None:
        return
    interrupted = getattr(cancel, "raise_if_interrupted", None)
    if callable(interrupted):
        interrupted()
        return
    cancelled = getattr(cancel, "raise_if_cancelled", None)
    if callable(cancelled):
        cancelled()
