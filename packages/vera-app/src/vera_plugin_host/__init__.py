"""Lightweight JSON-lines ingest worker for a user-selected Python environment.

The packaged desktop app ships this package as an extra resource and launches
it with an external interpreter. That interpreter must provide ``vera-ingest``
and any ingest plugins; it does not need ``vera-app``.
"""

from .worker import PROTOCOL_VERSION, main

__all__ = ["PROTOCOL_VERSION", "main"]
