from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE_PATHS = [
    ROOT / "packages" / "vera-doc" / "src",
    ROOT / "packages" / "vera-cli" / "src",
    ROOT / "packages" / "vera-ingest" / "src",
    ROOT / "packages" / "vera-ingest-pymupdf" / "src",
    ROOT / "packages" / "vera-app" / "src",
    ROOT / "tests",
]


def pytest_configure() -> None:
    existing = os.environ.get("PYTHONPATH", "")
    parts = [str(path) for path in SOURCE_PATHS]
    if existing:
        parts.append(existing)
    os.environ["PYTHONPATH"] = os.pathsep.join(parts)
