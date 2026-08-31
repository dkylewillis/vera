"""Filesystem layout, locking, and .vera discovery for library indexes."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import shutil
import sys
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

INDEX_DIRECTORY = ".vera-index"
INDEX_DATABASE = "index.sqlite3"
INDEX_POINTER = "current.json"
INDEX_GENERATIONS = "generations"
INDEX_VERSION = 1
INDEX_LOCK = "build.lock"


def _index_path(root: Path) -> Path:
    return root / INDEX_DIRECTORY


def _generation_path(root: Path) -> Path:
    index_root = _index_path(root)
    pointer = index_root / INDEX_POINTER
    if pointer.is_file():
        try:
            generation = json.loads(pointer.read_text(encoding="utf-8"))["generation"]
            if not isinstance(generation, str) or Path(generation).name != generation:
                raise ValueError("invalid generation")
            return index_root / INDEX_GENERATIONS / generation
        except (OSError, ValueError, KeyError, json.JSONDecodeError, TypeError):
            return index_root / "__invalid_generation__"
    return index_root


def _database_path(root: Path) -> Path:
    return _generation_path(root) / INDEX_DATABASE


def _path_size(path: Path) -> int:
    """Return the total byte size of a file or directory tree."""
    if path.is_file():
        return path.stat().st_size
    total = 0
    if path.is_dir():
        for child in path.rglob("*"):
            if child.is_file():
                total += child.stat().st_size
    return total


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _exclusive_lock(handle: Any) -> None:
    try:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            handle.write(b"\0")
            handle.flush()
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    except OSError:
        return


def _exclusive_unlock(handle: Any) -> None:
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
def _index_build_lock(target: Path) -> Iterator[None]:
    target.mkdir(parents=True, exist_ok=True)
    lock_path = target / INDEX_LOCK
    handle = open(lock_path, "a+b")
    try:
        _exclusive_lock(handle)
        yield
    finally:
        _exclusive_unlock(handle)
        handle.close()


def _gc_index_generations(target: Path, current: str) -> None:
    generations = target / INDEX_GENERATIONS
    if not generations.is_dir():
        return
    for child in generations.iterdir():
        if not child.is_dir() or child.name == current:
            continue
        shutil.rmtree(child, ignore_errors=True)


def _path_matches(relative_path: str, patterns: tuple[str, ...]) -> bool:
    """Return True when ``relative_path`` matches any exclude/include pattern."""
    parts = relative_path.split("/")
    for pattern in patterns:
        normalized = pattern.replace("\\", "/").strip("/")
        if not normalized:
            continue
        if fnmatch.fnmatch(relative_path, normalized):
            return True
        if any(fnmatch.fnmatch(part, normalized) for part in parts):
            return True
        if normalized.endswith("/**") and relative_path.startswith(
            normalized[:-3].rstrip("/") + "/"
        ):
            return True
    return False


def _excluded(relative_path: str, excludes: tuple[str, ...]) -> bool:
    return _path_matches(relative_path, excludes)


def _included(relative_path: str, includes: tuple[str, ...]) -> bool:
    if not includes:
        return True
    return _path_matches(relative_path, includes)


def discover_vera_files(
    directory: str | Path,
    *,
    recursive: bool = False,
    excludes: Iterable[str] = (),
    includes: Iterable[str] = (),
) -> list[Path]:
    """Discover unique .vera files without following directory symlinks.

    When ``includes`` is empty, every discovered archive is a candidate.
    When any include is present, a file must match at least one include and
    no exclude. Include matching uses the same glob / path-component / ``/**``
    rules as excludes. Directory pruning still follows excludes only, so a
    nested include can match under an unexcluded parent.
    """
    root = Path(directory).resolve()
    if not root.is_dir():
        raise NotADirectoryError(str(directory))
    exclude_patterns = tuple(excludes)
    include_patterns = tuple(includes)
    if recursive:
        candidates: list[Path] = []
        for current, directories, filenames in os.walk(root, followlinks=False):
            current_path = Path(current)
            kept_directories = []
            for name in directories:
                child = current_path / name
                relative_child = _relative(child, root)
                if child.is_symlink() or _excluded(relative_child, exclude_patterns):
                    continue
                kept_directories.append(name)
            directories[:] = kept_directories
            candidates.extend(
                current_path / name for name in filenames if name.lower().endswith(".vera")
            )
    else:
        candidates = [path for path in root.iterdir() if path.suffix.lower() == ".vera"]
    discovered: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        try:
            if not candidate.is_file() or candidate.is_symlink():
                continue
            relative_path = _relative(candidate, root)
            if _excluded(relative_path, exclude_patterns):
                continue
            if not _included(relative_path, include_patterns):
                continue
            resolved = candidate.resolve()
            key = os.path.normcase(str(resolved))
            if key in seen:
                continue
            seen.add(key)
            discovered.append(resolved)
        except (OSError, ValueError):
            continue
    return sorted(discovered, key=lambda path: _relative(path, root).lower())


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
