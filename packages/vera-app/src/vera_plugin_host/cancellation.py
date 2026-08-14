from __future__ import annotations

import threading
from typing import Any


class CancelledError(RuntimeError):
    """Raised when a user cancels in-flight plugin-host work."""


class SkipCurrentError(RuntimeError):
    """Raised when a user skips the current conversion item."""


class CancellationToken:
    """Cooperatively cancel or skip conversion work in the plugin host."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._skip_event = threading.Event()
        self._lock = threading.Lock()
        self._response: Any | None = None

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    @property
    def skip_requested(self) -> bool:
        return self._skip_event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise CancelledError()

    def raise_if_interrupted(self) -> None:
        self.raise_if_cancelled()
        if self.skip_requested:
            raise SkipCurrentError("File skipped")

    def _close_response(self) -> None:
        with self._lock:
            response = self._response
        if response is not None:
            try:
                response.close()
            except Exception:
                pass

    def cancel(self) -> None:
        self._event.set()
        self._close_response()

    def skip(self) -> None:
        self._skip_event.set()
        self._close_response()

    def clear_skip(self) -> None:
        self._skip_event.clear()

    def register_response(self, response: Any) -> None:
        with self._lock:
            if self.cancelled or self.skip_requested:
                try:
                    response.close()
                except Exception:
                    pass
                self.raise_if_interrupted()
            self._response = response

    def unregister_response(self, response: Any) -> None:
        with self._lock:
            if self._response is response:
                self._response = None
