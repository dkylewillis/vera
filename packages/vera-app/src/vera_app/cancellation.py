from __future__ import annotations

import threading
from typing import Any


class CancelledError(RuntimeError):
    """Raised when a user cancels an in-flight answer."""


class CancellationToken:
    """Cooperatively cancel work and interrupt its active HTTP response."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._response: Any | None = None

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise CancelledError("Answer cancelled")

    def cancel(self) -> None:
        self._event.set()
        with self._lock:
            response = self._response
        if response is not None:
            try:
                response.close()
            except Exception:
                pass

    def register_response(self, response: Any) -> None:
        with self._lock:
            if self.cancelled:
                try:
                    response.close()
                except Exception:
                    pass
                raise CancelledError("Answer cancelled")
            self._response = response

    def unregister_response(self, response: Any) -> None:
        with self._lock:
            if self._response is response:
                self._response = None
