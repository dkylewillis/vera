"""Short convert/Docling timing lines on stderr.

Desktop Electron tees sidecar stderr into ``userData/logs/sidecar.log``.
CLI users see the same lines on stderr. Lines never include PDF text, tokens,
or secrets.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def format_timing_line(step: str, elapsed_ms: int | None = None, **fields: Any) -> str:
    parts = [f"{utc_timestamp()} timing step={step}"]
    if elapsed_ms is not None:
        parts.append(f"elapsed_ms={int(elapsed_ms)}")
    for key, value in fields.items():
        if value is None or value == "":
            continue
        text = str(value).replace(" ", "_")
        parts.append(f"{key}={text}")
    return " ".join(parts)


def log_event(step: str, elapsed_ms: int | None = None, **fields: Any) -> None:
    print(format_timing_line(step, elapsed_ms, **fields), file=sys.stderr, flush=True)


@contextmanager
def timed_step(step: str, **fields: Any) -> Iterator[dict[str, Any]]:
    """Time a block; extra ``fields`` may be filled in during the block.

    Emits a start line (no ``elapsed_ms``) so long steps are visible in the
    log before they finish.
    """
    extras: dict[str, Any] = dict(fields)
    log_event(step, **extras)
    started = time.perf_counter()
    try:
        yield extras
    finally:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        log_event(step, elapsed_ms, **extras)
