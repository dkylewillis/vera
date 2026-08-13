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


def clear_user_skip(cancel: Any | None) -> None:
    """Consume a one-shot skip request so it cannot leak onto the next file."""
    if cancel is None:
        return
    clear = getattr(cancel, "clear_skip", None)
    if callable(clear):
        clear()


def is_user_skip_error(exc: BaseException) -> bool:
    """Return True when ``exc`` is a real skip/interrupt, not a leftover flag.

    Sidecar skip uses ``SkipCurrentError``. Classification must not treat
    ``skip_requested`` on an unrelated exception as a user skip.
    """
    return type(exc).__name__ == "SkipCurrentError"
