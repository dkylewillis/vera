from __future__ import annotations

import pytest

from vera_app.cancellation import (
    CancellationToken,
    CancelledError,
    SkipCurrentError,
)


class _FakeResponse:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_cancel_takes_precedence_over_skip():
    token = CancellationToken()
    token.skip()
    token.cancel()

    with pytest.raises(CancelledError):
        token.raise_if_interrupted()


def test_skip_raises_until_cleared():
    token = CancellationToken()
    token.skip()

    with pytest.raises(SkipCurrentError, match="File skipped"):
        token.raise_if_interrupted()

    token.clear_skip()
    token.raise_if_interrupted()


def test_skip_closes_registered_response():
    token = CancellationToken()
    response = _FakeResponse()
    token.register_response(response)

    token.skip()

    assert response.closed is True
    with pytest.raises(SkipCurrentError):
        token.raise_if_interrupted()


def test_register_response_closes_and_raises_when_already_cancelled():
    token = CancellationToken()
    token.cancel()
    response = _FakeResponse()

    with pytest.raises(CancelledError):
        token.register_response(response)

    assert response.closed is True
