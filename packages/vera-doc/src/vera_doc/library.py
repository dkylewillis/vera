"""On-disk layout for managed folder libraries.

A managed library keeps source documents where the user put them and stores
derived archives, the search index, and recoverable deletions under ``.vera/``.
This module has no ingest dependency. Conversion and sync live in
``vera-ingest``.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LIBRARY_DIRECTORY = ".vera"
LIBRARY_MANIFEST = "library.json"
LIBRARY_README = "README.txt"
LIBRARY_STATE = "state.json"
LIBRARY_LOCK = "sync.lock"
LIBRARY_ARCHIVES = "archives"
LIBRARY_INDEX = "index"
LIBRARY_TRASH = "trash"
LAYOUT_VERSION = 1
DEFAULT_TRASH_RETENTION_DAYS = 30
MASS_DELETE_FRACTION = 0.20
MASS_DELETE_MIN_COUNT = 5
ARCHIVE_SUFFIX = ".vera"

LIBRARY_README_TEXT = """This folder is managed by VERA.

It stores searchable archives, a rebuildable search index, and recently
deleted archives. Your documents stay in the folders next to this one.
Deleting this folder removes search data only. It does not delete those
documents. You can rebuild search by pointing VERA at the library again.
"""


class LibraryError(RuntimeError):
    """Base error for managed-library layout operations."""


class LibraryExistsError(LibraryError):
    """The folder is already a managed library."""


class NestedLibraryError(LibraryError):
    """A managed library would sit inside another managed library."""


class LibraryNotFoundError(LibraryError):
    """The folder is not a managed library."""


class LibraryBusyError(LibraryError):
    """Another sync holds this library's lock."""


class LibraryUnreachableError(LibraryError):
    """The library root could not be listed."""


def library_dir(root: Path) -> Path:
    return Path(root) / LIBRARY_DIRECTORY


def library_manifest_path(root: Path) -> Path:
    return library_dir(root) / LIBRARY_MANIFEST


def is_managed_library(root: str | Path) -> bool:
    """Return True when ``root`` itself contains ``.vera/library.json``."""
    return library_manifest_path(Path(root)).is_file()


def find_library_root(path: str | Path) -> Path | None:
    """Walk parents for ``.vera/library.json``, the way Git finds ``.git``.

    ``path`` may be a file or a directory. The nearest containing library wins.
    """
    current = Path(path).resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if library_manifest_path(candidate).is_file():
            return candidate
    return None


def normalize_source_rel(source_rel: str) -> str:
    """Return a forward-slash path relative to the library root."""
    normalized = source_rel.replace("\\", "/").strip("/")
    if not normalized or normalized.startswith("../") or "/../" in f"/{normalized}/":
        raise ValueError(f"source path is not inside the library: {source_rel}")
    if any(part in {".", ".."} for part in normalized.split("/")):
        raise ValueError(f"source path is not inside the library: {source_rel}")
    return normalized


def archive_path_for(root: str | Path, source_rel: str) -> Path:
    """Return ``.vera/archives/<source><.vera>`` for a library-relative source."""
    relative = normalize_source_rel(source_rel)
    return library_dir(root) / LIBRARY_ARCHIVES / f"{relative}{ARCHIVE_SUFFIX}"


def source_path_for(archive_rel: str) -> str | None:
    """Map a library-relative archive path back to its source path.

    ``.vera/archives/Plans/Site Plan.pdf.vera`` becomes ``Plans/Site Plan.pdf``.
    Paths outside ``.vera/archives/`` return None so unmanaged archives keep
    their own relative paths.
    """
    normalized = archive_rel.replace("\\", "/").strip("/")
    prefix = f"{LIBRARY_DIRECTORY}/{LIBRARY_ARCHIVES}/"
    if not normalized.startswith(prefix):
        return None
    inner = normalized[len(prefix) :]
    if not inner.lower().endswith(ARCHIVE_SUFFIX):
        return None
    source = inner[: -len(ARCHIVE_SUFFIX)]
    if not source or source.endswith("/"):
        return None
    return source


def strip_extended_path(path: str | Path) -> str:
    """Remove a Windows ``\\\\?\\`` prefix so the path can be used in URIs."""
    text = str(path)
    if text.startswith("\\\\?\\UNC\\"):
        return "\\\\" + text[len("\\\\?\\UNC\\") :]
    if text.startswith("\\\\?\\"):
        return text[len("\\\\?\\") :]
    return text


def extended_path(path: str | Path) -> str:
    """Return a path string that can address deep Windows trees.

    The ``\\\\?\\`` prefix opts into long paths without a registry setting.
    Other platforms return the absolute path unchanged.
    """
    text = os.path.abspath(path)
    if os.name != "nt":
        return text
    if text.startswith("\\\\?\\"):
        return text
    if text.startswith("\\\\"):
        return "\\\\?\\UNC\\" + text[2:]
    return "\\\\?\\" + text


def hide_directory(path: Path) -> None:
    """Mark a directory hidden on Windows. Other platforms use the leading dot."""
    if sys.platform != "win32":
        return
    import ctypes

    FILE_ATTRIBUTE_HIDDEN = 0x02
    ctypes.windll.kernel32.SetFileAttributesW(str(path), FILE_ATTRIBUTE_HIDDEN)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_convert_settings(
    *,
    model: str = "hashing",
    parser: str | None = None,
    pipeline_options: Mapping[str, Any] | None = None,
    embedder_options: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "model": model,
        "parser": parser,
        "pipeline_options": dict(pipeline_options or {}),
        "embedder_options": dict(embedder_options or {}),
        "metadata": dict(metadata or {}),
    }


def new_manifest(
    *,
    model: str = "hashing",
    parser: str | None = None,
    pipeline_options: Mapping[str, Any] | None = None,
    embedder_options: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    trash_retention_days: int = DEFAULT_TRASH_RETENTION_DAYS,
) -> dict[str, Any]:
    if trash_retention_days < 0:
        raise ValueError("trash_retention_days must be non-negative")
    return {
        "library_id": uuid.uuid4().hex,
        "layout_version": LAYOUT_VERSION,
        "created_at": _utc_now(),
        "trash_retention_days": trash_retention_days,
        "convert": default_convert_settings(
            model=model,
            parser=parser,
            pipeline_options=pipeline_options,
            embedder_options=embedder_options,
            metadata=metadata,
        ),
    }


def read_manifest(root: str | Path) -> dict[str, Any]:
    path = library_manifest_path(root)
    if not path.is_file():
        raise LibraryNotFoundError(f"No managed library at {root}")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LibraryError(f"Unable to read {path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise LibraryError(f"Invalid library manifest: {path}")
    if manifest.get("layout_version") != LAYOUT_VERSION:
        raise LibraryError(
            f"Unsupported library layout version: {manifest.get('layout_version')}"
        )
    manifest.setdefault("trash_retention_days", DEFAULT_TRASH_RETENTION_DAYS)
    convert = manifest.get("convert")
    if not isinstance(convert, dict):
        manifest["convert"] = default_convert_settings()
    return manifest


def write_manifest(root: str | Path, manifest: Mapping[str, Any]) -> None:
    target = library_manifest_path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f"{target.name}.tmp-{uuid.uuid4().hex}")
    temporary.write_text(json.dumps(dict(manifest), indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, target)


def read_state(root: str | Path) -> dict[str, dict[str, Any]]:
    path = library_dir(root) / LIBRARY_STATE
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    files = payload.get("files") if isinstance(payload, dict) else None
    if not isinstance(files, dict):
        return {}
    return {str(key): value for key, value in files.items() if isinstance(value, dict)}


def write_state(root: str | Path, files: Mapping[str, Mapping[str, Any]]) -> None:
    target = library_dir(root) / LIBRARY_STATE
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f"{target.name}.tmp-{uuid.uuid4().hex}")
    temporary.write_text(
        json.dumps({"files": {key: dict(value) for key, value in files.items()}}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temporary, target)


def _try_lock(handle: Any) -> bool:
    try:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            if not handle.read(1):
                handle.seek(0)
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _unlock(handle: Any) -> None:
    try:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        return


@contextmanager
def sync_lock(root: str | Path) -> Iterator[None]:
    """Hold ``.vera/sync.lock`` for one sync. A second holder raises."""
    target = library_dir(root)
    target.mkdir(parents=True, exist_ok=True)
    lock_path = target / LIBRARY_LOCK
    handle = open(extended_path(lock_path), "a+b")
    locked = False
    try:
        locked = _try_lock(handle)
        if not locked:
            raise LibraryBusyError(f"Library is already syncing: {root}")
        yield
    finally:
        if locked:
            _unlock(handle)
        handle.close()
