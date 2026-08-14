"""Shared sidecar request/response aliases."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

Request = dict[str, Any]
Response = dict[str, Any]
Handler = Callable[[Request], Any]
WriteEvent = Callable[[dict[str, Any]], None]
