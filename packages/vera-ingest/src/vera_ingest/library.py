"""Create and sync a managed folder library.

Source documents stay in the user's folders. VERA keeps a mirrored archive
under ``.vera/archives/``, moves archives when a file is renamed or moved,
and parks deleted archives in ``.vera/trash/`` instead of destroying them.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from vera_doc import build_library_index, library_index_status, update_library_index
from vera_doc.document import VeraDocument
from vera_doc.library import (
    ARCHIVE_SUFFIX,
    LIBRARY_ARCHIVES,
    LIBRARY_DIRECTORY,
    LIBRARY_README,
    LIBRARY_README_TEXT,
    LIBRARY_TRASH,
    MASS_DELETE_FRACTION,
    MASS_DELETE_MIN_COUNT,
    LibraryBusyError,
    LibraryError,
    LibraryExistsError,
    LibraryNotFoundError,
    LibraryUnreachableError,
    NestedLibraryError,
    archive_path_for,
    extended_path,
    strip_extended_path,
    find_library_root,
    hide_directory,
    is_managed_library,
    library_dir,
    new_manifest,
    read_manifest,
    read_state,
    sync_lock,
    write_manifest,
    write_state,
)

from .cancellation import raise_if_cancelled
from .convert import _stored_source_file_hash, convert
from .formats import installed_source_formats, source_suffix
from .viewer import export_source_document

TRASH_STAMP_FORMAT = "%Y%m%dT%H%M%S%fZ"
Progress = Callable[[dict[str, Any]], None]


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(extended_path(path), "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _stat(path: Path) -> os.stat_result:
    return os.stat(extended_path(path))


def _is_file(path: Path) -> bool:
    try:
        return os.path.isfile(extended_path(path) if os.name == "nt" else path)
    except OSError:
        return False


def _source_suffixes(parser: str | None) -> set[str]:
    if parser:
        from .formats import pipeline_source_formats

        suffixes = set(pipeline_source_formats(parser))
    else:
        suffixes = set(installed_source_formats())
    if not suffixes:
        raise ValueError("No installed ingest pipeline advertises source formats to convert.")
    return suffixes


def _walk_root(root: Path) -> str:
    return extended_path(root) if os.name == "nt" else str(root)


def discover_sources(root: Path, suffixes: set[str]) -> list[tuple[str, Path]]:
    """Return ``(relative source path, absolute path)`` pairs, skipping ``.vera``."""
    found: list[tuple[str, Path]] = []
    root_plain = Path(strip_extended_path(root.resolve()))
    try:
        for current, directories, filenames in os.walk(_walk_root(root), followlinks=False):
            current_plain = Path(strip_extended_path(current))
            kept: list[str] = []
            for name in directories:
                child = Path(extended_path(current_plain / name)) if os.name == "nt" else current_plain / name
                if name.startswith(".") or Path(child).is_symlink():
                    continue
                kept.append(name)
            directories[:] = sorted(kept)
            for name in sorted(filenames):
                path = current_plain / name
                try:
                    if path.is_symlink() or not _is_file(path):
                        continue
                except OSError:
                    continue
                if source_suffix(path) not in suffixes:
                    continue
                found.append((path.relative_to(root_plain).as_posix(), path))
    except OSError as exc:
        raise LibraryUnreachableError(f"Library root is unreachable: {exc}") from exc
    return found


def _list_archives(root: Path) -> list[tuple[str, Path]]:
    archives = library_dir(root) / LIBRARY_ARCHIVES
    if not archives.is_dir():
        return []
    found: list[tuple[str, Path]] = []
    archives_plain = Path(strip_extended_path(archives.resolve()))
    for current, _directories, filenames in os.walk(_walk_root(archives), followlinks=False):
        current_plain = Path(strip_extended_path(current))
        for name in filenames:
            if not name.lower().endswith(ARCHIVE_SUFFIX):
                continue
            path = current_plain / name
            if path.is_symlink() or not _is_file(path):
                continue
            relative = path.relative_to(archives_plain).as_posix()
            found.append((relative[: -len(ARCHIVE_SUFFIX)], path))
    return found


def _nested_child(root: Path) -> Path | None:
    resolved = root.resolve()
    for current, directories, _filenames in os.walk(resolved):
        current_path = Path(current)
        if current_path != resolved and is_managed_library(current_path):
            return current_path
        directories[:] = [
            name
            for name in directories
            if name != LIBRARY_DIRECTORY
            and not name.startswith(".")
            and not (current_path / name).is_symlink()
        ]
    return None


def _empty_report(root: Path, *, dry_run: bool) -> dict[str, Any]:
    return {
        "ok": True,
        "managed": True,
        "directory": str(root),
        "dry_run": dry_run,
        "needs_confirmation": False,
        "converted": 0,
        "moved": 0,
        "trashed": 0,
        "pending_trash": 0,
        "purged": 0,
        "skipped": 0,
        "failed": 0,
        "adopted": 0,
        "actions": [],
        "errors": [],
    }


def init_library(
    directory: str,
    *,
    adopt: bool = False,
    model: str = "hashing",
    parser: str | None = None,
    pipeline_options: Mapping[str, Any] | None = None,
    embedder_options: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    trash_retention_days: int = 30,
) -> dict[str, Any]:
    """Create ``.vera/`` for a folder of source documents.

    Refuses to create a library inside an existing one, or a library that
    would contain another. ``adopt`` moves sibling ``.vera`` files whose
    stored source hash matches into ``.vera/archives/``.
    """
    root = Path(directory).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(str(directory))
    if is_managed_library(root):
        raise LibraryExistsError(f"This folder is already a VERA library: {root}")
    if root.parent != root:
        parent = find_library_root(root.parent)
        if parent is not None:
            raise NestedLibraryError(
                f"{root} is inside the library at {parent}. "
                "Search that library and scope to this folder instead."
            )
    child = _nested_child(root)
    if child is not None:
        raise NestedLibraryError(
            f"{root} already contains a library at {child}. Use that library, or remove it first."
        )

    manifest = new_manifest(
        model=model,
        parser=parser,
        pipeline_options=pipeline_options,
        embedder_options=embedder_options,
        metadata=metadata,
        trash_retention_days=trash_retention_days,
    )
    vera_dir = library_dir(root)
    vera_dir.mkdir(parents=True, exist_ok=True)
    (vera_dir / LIBRARY_ARCHIVES).mkdir(exist_ok=True)
    (vera_dir / LIBRARY_TRASH).mkdir(exist_ok=True)
    (vera_dir / LIBRARY_README).write_text(LIBRARY_README_TEXT, encoding="utf-8")
    write_manifest(root, manifest)
    hide_directory(vera_dir)

    adopted: list[str] = []
    errors: list[dict[str, str]] = []
    if adopt:
        adopted, errors = _adopt_siblings(root, _source_suffixes(parser))
    return {
        "ok": not errors,
        "managed": True,
        "directory": str(root),
        "library_id": manifest["library_id"],
        "adopted": adopted,
        "failed": len(errors),
        "errors": errors,
    }


def _adopt_siblings(root: Path, suffixes: set[str]) -> tuple[list[str], list[dict[str, str]]]:
    adopted: list[str] = []
    errors: list[dict[str, str]] = []
    try:
        sources = discover_sources(root, suffixes)
    except LibraryUnreachableError as exc:
        return [], [{"input": str(root), "error": str(exc)}]
    for source_rel, source in sources:
        sibling = source.with_suffix(ARCHIVE_SUFFIX)
        destination = archive_path_for(root, source_rel)
        if destination.exists() or not sibling.is_file():
            continue
        stored = _stored_source_file_hash(sibling)
        try:
            current = _hash_file(source)
        except OSError as exc:
            errors.append({"input": source_rel, "error": str(exc)})
            continue
        if stored is None or stored != current:
            continue
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(extended_path(sibling), extended_path(destination))
        except OSError as exc:
            errors.append({"input": source_rel, "error": str(exc)})
            continue
        adopted.append(source_rel)
    return adopted, errors


def _parse_trash_stamp(name: str) -> datetime | None:
    try:
        return datetime.strptime(name, TRASH_STAMP_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _purge_trash(root: Path, retention_days: int) -> list[str]:
    trash = library_dir(root) / LIBRARY_TRASH
    if not trash.is_dir() or retention_days < 0:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    purged: list[str] = []
    for child in list(trash.iterdir()):
        if not child.is_dir():
            continue
        stamped = _parse_trash_stamp(child.name)
        if stamped is None or stamped >= cutoff:
            continue
        shutil.rmtree(child, ignore_errors=True)
        purged.append(child.name)
    return purged


def _plan(root: Path, *, reconvert: bool) -> dict[str, Any]:
    manifest = read_manifest(root)
    parser = manifest.get("convert", {}).get("parser")
    suffixes = _source_suffixes(parser if isinstance(parser, str) else None)
    sources = discover_sources(root, suffixes)
    source_map = dict(sources)
    archives = _list_archives(root)
    archive_map = dict(archives)
    state = read_state(root)
    hash_cache: dict[Path, str | None] = {}

    def stored_hash(path: Path) -> str | None:
        if path not in hash_cache:
            hash_cache[path] = _stored_source_file_hash(path)
        return hash_cache[path]

    unchanged: list[dict[str, Any]] = []
    converts: list[dict[str, Any]] = []
    unmatched_sources: list[tuple[str, Path]] = []

    for source_rel, source in sources:
        archive = archive_map.get(source_rel)
        if archive is None or not archive.is_file():
            unmatched_sources.append((source_rel, source))
            continue
        try:
            stat = _stat(source)
        except OSError as exc:
            converts.append(
                {"action": "convert", "source": source_rel, "error": str(exc), "hash": None}
            )
            continue
        recorded = state.get(source_rel) or {}
        same_stat = (
            recorded.get("size") == stat.st_size and recorded.get("mtime_ns") == stat.st_mtime_ns
        )
        if same_stat and not reconvert:
            unchanged.append(
                {
                    "action": "unchanged",
                    "source": source_rel,
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                    "hash": recorded.get("hash"),
                }
            )
            continue
        try:
            digest = _hash_file(source)
        except OSError as exc:
            converts.append({"action": "convert", "source": source_rel, "error": str(exc)})
            continue
        if stored_hash(archive) == digest and not reconvert:
            unchanged.append(
                {
                    "action": "unchanged",
                    "source": source_rel,
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                    "hash": digest,
                }
            )
            continue
        converts.append(
            {
                "action": "convert",
                "source": source_rel,
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "hash": digest,
            }
        )

    unmatched_archives = {
        source_rel: path
        for source_rel, path in archives
        if source_rel not in source_map
    }
    by_hash: dict[str, list[str]] = {}
    for source_rel, path in unmatched_archives.items():
        digest = stored_hash(path)
        if digest:
            by_hash.setdefault(digest, []).append(source_rel)

    moves: list[dict[str, Any]] = []
    claimed: set[str] = set()
    for source_rel, source in unmatched_sources:
        try:
            stat = _stat(source)
            digest = _hash_file(source)
        except OSError as exc:
            converts.append({"action": "convert", "source": source_rel, "error": str(exc)})
            continue
        candidates = []
        for old_rel in by_hash.get(digest, []):
            if old_rel in claimed:
                continue
            recorded = state.get(old_rel) or {}
            if recorded.get("size") not in (None, stat.st_size):
                continue
            candidates.append(old_rel)
        if len(candidates) > 1:
            named = [
                old_rel
                for old_rel in candidates
                if Path(old_rel).name.lower() == Path(source_rel).name.lower()
            ]
            candidates = named if len(named) == 1 else []
        if len(candidates) == 1:
            old_rel = candidates[0]
            claimed.add(old_rel)
            moves.append(
                {
                    "action": "move",
                    "source": source_rel,
                    "from": old_rel,
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                    "hash": digest,
                }
            )
        else:
            converts.append(
                {
                    "action": "convert",
                    "source": source_rel,
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                    "hash": digest,
                }
            )

    trashes = [
        {"action": "trash", "source": source_rel}
        for source_rel in sorted(unmatched_archives)
        if source_rel not in claimed
    ]
    archive_count = len(archives)
    needs_confirmation = bool(
        archive_count
        and len(trashes) > MASS_DELETE_MIN_COUNT
        and (len(trashes) / archive_count) > MASS_DELETE_FRACTION
    )
    return {
        "manifest": manifest,
        "unchanged": unchanged,
        "converts": converts,
        "moves": moves,
        "trashes": trashes,
        "needs_confirmation": needs_confirmation,
        "archive_count": archive_count,
    }


def _convert_one(
    root: Path,
    source_rel: str,
    manifest: Mapping[str, Any],
    *,
    cancel: Any | None,
) -> None:
    settings = manifest.get("convert") if isinstance(manifest.get("convert"), dict) else {}
    source = root / source_rel
    destination = archive_path_for(root, source_rel)
    output = extended_path(destination) if os.name == "nt" and len(str(destination)) >= 240 else str(destination)
    convert(
        extended_path(source) if os.name == "nt" and len(str(source)) >= 240 else str(source),
        output,
        model=str(settings.get("model") or "hashing"),
        parser=settings.get("parser") if isinstance(settings.get("parser"), str) else None,
        pipeline_options=settings.get("pipeline_options") or None,
        embedder_options=settings.get("embedder_options") or None,
        metadata=settings.get("metadata") or None,
        cancel=cancel,
    )


def _apply_plan(
    root: Path,
    plan: dict[str, Any],
    *,
    dry_run: bool,
    confirm_deletes: bool,
    cancel: Any | None,
    progress: Progress | None,
) -> dict[str, Any]:
    report = _empty_report(root, dry_run=dry_run)
    report["needs_confirmation"] = bool(plan["needs_confirmation"]) and not confirm_deletes
    hold_trash = dry_run or report["needs_confirmation"]
    actions: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    state_files: dict[str, dict[str, Any]] = {}
    manifest = plan["manifest"]
    steps = [*plan["moves"], *plan["converts"]]
    if not hold_trash:
        steps.extend(plan["trashes"])
    total = len(steps)
    for index, step in enumerate(steps):
        raise_if_cancelled(cancel)
        if progress:
            progress(
                {
                    "phase": step["action"],
                    "completed": index,
                    "total": total,
                    "input": step.get("source") or "",
                }
            )
        source_rel = str(step["source"])
        try:
            if step["action"] == "move" and not dry_run:
                destination = archive_path_for(root, source_rel)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(
                    extended_path(archive_path_for(root, str(step["from"]))),
                    extended_path(destination),
                )
            elif step["action"] == "convert" and not dry_run:
                if step.get("error"):
                    raise OSError(step["error"])
                _convert_one(root, source_rel, manifest, cancel=cancel)
            elif step["action"] == "trash" and not dry_run:
                _trash_archive(root, source_rel)
        except Exception as exc:
            if cancel is not None and getattr(cancel, "cancelled", False):
                raise
            errors.append({"input": source_rel, "error": str(exc)})
            continue
        actions.append({key: value for key, value in step.items() if key != "error"})
        if step["action"] in {"move", "convert", "unchanged"} and step.get("size") is not None:
            state_files[source_rel] = {
                "size": step.get("size"),
                "mtime_ns": step.get("mtime_ns"),
                "hash": step.get("hash"),
            }
        if step["action"] == "move":
            report["moved"] += 1
        elif step["action"] == "convert":
            report["converted"] += 1
        elif step["action"] == "trash":
            report["trashed"] += 1

    for step in plan["unchanged"]:
        actions.append(step)
        report["skipped"] += 1
        state_files[str(step["source"])] = {
            "size": step.get("size"),
            "mtime_ns": step.get("mtime_ns"),
            "hash": step.get("hash"),
        }
    if hold_trash:
        report["pending_trash"] = len(plan["trashes"])
        if dry_run:
            actions.extend(plan["trashes"])
    if not dry_run:
        retention = int(manifest.get("trash_retention_days", 30))
        report["purged"] = len(_purge_trash(root, retention))
        write_state(root, state_files)
    report["actions"] = actions
    report["errors"] = errors
    report["failed"] = len(errors)
    report["ok"] = not errors
    return report


def _trash_archive(root: Path, source_rel: str) -> None:
    archive = archive_path_for(root, source_rel)
    if not archive.is_file():
        return
    stamp = datetime.now(timezone.utc).strftime(TRASH_STAMP_FORMAT)
    destination = library_dir(root) / LIBRARY_TRASH / stamp / f"{source_rel}{ARCHIVE_SUFFIX}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(extended_path(archive), extended_path(destination))


def _refresh_index(root: Path, progress: Progress | None) -> dict[str, Any]:
    status = library_index_status(str(root), verify_hashes=False)
    if status.get("exists"):
        try:
            return update_library_index(str(root), progress=progress)
        except FileNotFoundError:
            pass
    return build_library_index(str(root), recursive=True, progress=progress)


def _library_root_for(directory: str) -> tuple[Path, Path | None]:
    """Return ``(requested, managed root or None)``."""
    requested = Path(directory).expanduser().resolve()
    if not requested.is_dir():
        raise NotADirectoryError(str(directory))
    return requested, find_library_root(requested)


def library_status(directory: str) -> dict[str, Any]:
    """Describe a folder and, when it is managed, the pending sync plan.

    A folder inside a managed library reports that library. Does not take the
    sync lock and does not modify anything.
    """
    requested, parent = _library_root_for(directory)
    root = parent or requested
    if parent is not None and parent != requested:
        report = library_status(str(parent))
        report["inside_library"] = True
        report["requested"] = str(requested)
        return report
    if not root.is_dir():
        raise NotADirectoryError(str(directory))
    if not is_managed_library(root):
        suffixes = _source_suffixes(None)
        try:
            sources = discover_sources(root, suffixes)
        except LibraryUnreachableError as exc:
            return {
                "ok": False,
                "managed": False,
                "directory": str(root),
                "inside_library": parent is not None,
                "library_root": str(parent) if parent else None,
                "needs_confirmation": True,
                "error": str(exc),
                "adoptable": [],
            }
        adoptable = []
        for source_rel, source in sources:
            sibling = source.with_suffix(ARCHIVE_SUFFIX)
            if not sibling.is_file():
                continue
            stored = _stored_source_file_hash(sibling)
            try:
                current = _hash_file(source)
            except OSError:
                continue
            if stored and stored == current:
                adoptable.append(source_rel)
        return {
            "ok": True,
            "managed": False,
            "directory": str(root),
            "inside_library": parent is not None and parent != root,
            "library_root": str(parent) if parent else None,
            "needs_confirmation": False,
            "adoptable": adoptable,
        }
    try:
        plan = _plan(root, reconvert=False)
    except LibraryUnreachableError as exc:
        return {
            "ok": False,
            "managed": True,
            "directory": str(root),
            "inside_library": False,
            "library_root": str(root),
            "needs_confirmation": True,
            "error": str(exc),
            "adoptable": [],
        }
    report = _apply_plan(root, plan, dry_run=True, confirm_deletes=False, cancel=None, progress=None)
    report["inside_library"] = False
    report["library_root"] = str(root)
    report["library_id"] = plan["manifest"].get("library_id")
    report["trash"] = list_trash(str(root))["entries"]
    report["adoptable"] = []
    return report


def sync_library(
    directory: str,
    *,
    dry_run: bool = False,
    confirm_deletes: bool = False,
    reconvert: bool = False,
    progress: Progress | None = None,
    cancel: Any | None = None,
    require: bool = True,
) -> dict[str, Any]:
    """Reconcile ``.vera/archives`` with the source documents in ``directory``."""
    requested = Path(directory).expanduser().resolve()
    if requested.is_dir():
        located = find_library_root(requested)
        root = located or requested
    else:
        root = requested
    if not root.is_dir():
        if require:
            raise NotADirectoryError(str(directory))
        return {
            "ok": False,
            "managed": False,
            "directory": str(root),
            "needs_confirmation": True,
            "error": "library root is unreachable",
            "converted": 0,
            "moved": 0,
            "trashed": 0,
            "pending_trash": 0,
            "purged": 0,
            "skipped": 0,
            "failed": 0,
            "errors": [],
        }
    if not is_managed_library(root):
        if require:
            raise LibraryNotFoundError(f"No managed library at {root}")
        return {
            "ok": True,
            "managed": False,
            "directory": str(root),
            "needs_confirmation": False,
            "converted": 0,
            "moved": 0,
            "trashed": 0,
            "pending_trash": 0,
            "purged": 0,
            "skipped": 0,
            "failed": 0,
            "errors": [],
        }
    if dry_run:
        try:
            plan = _plan(root, reconvert=reconvert)
        except LibraryUnreachableError as exc:
            report = _empty_report(root, dry_run=True)
            report["ok"] = False
            report["needs_confirmation"] = True
            report["error"] = str(exc)
            return report
        return _apply_plan(
            root, plan, dry_run=True, confirm_deletes=confirm_deletes, cancel=cancel, progress=progress
        )

    try:
        lock = sync_lock(root)
        lock.__enter__()
    except LibraryBusyError:
        if require:
            raise
        return {
            "ok": True,
            "managed": True,
            "busy": True,
            "directory": str(root),
            "needs_confirmation": False,
            "converted": 0,
            "moved": 0,
            "trashed": 0,
            "pending_trash": 0,
            "purged": 0,
            "skipped": 0,
            "failed": 0,
            "errors": [],
        }
    try:
        adopted, adopt_errors = _adopt_siblings(root, _source_suffixes(_parser_from_manifest(root)))
        try:
            plan = _plan(root, reconvert=reconvert)
        except LibraryUnreachableError as exc:
            report = _empty_report(root, dry_run=False)
            report["ok"] = False
            report["needs_confirmation"] = True
            report["error"] = str(exc)
            report["adopted"] = len(adopted)
            return report
        report = _apply_plan(
            root,
            plan,
            dry_run=False,
            confirm_deletes=confirm_deletes,
            cancel=cancel,
            progress=progress,
        )
        report["adopted"] = len(adopted)
        if adopt_errors:
            report["errors"] = [*adopt_errors, *report["errors"]]
            report["failed"] = len(report["errors"])
            report["ok"] = False
        if report["needs_confirmation"] and not confirm_deletes:
            # Moves and conversions still landed. Deletions wait for confirmation.
            pass
        try:
            raise_if_cancelled(cancel)
            report["index"] = _refresh_index(root, progress)
        except Exception as exc:
            if cancel is not None and getattr(cancel, "cancelled", False):
                raise
            report["errors"] = [*report["errors"], {"input": ".vera/index", "error": str(exc)}]
            report["failed"] = len(report["errors"])
            report["ok"] = False
        return report
    finally:
        lock.__exit__(None, None, None)


def _parser_from_manifest(root: Path) -> str | None:
    try:
        parser = read_manifest(root).get("convert", {}).get("parser")
    except LibraryError:
        return None
    return parser if isinstance(parser, str) else None


def list_trash(directory: str) -> dict[str, Any]:
    """List recoverable archives under ``.vera/trash/``."""
    requested, located = _library_root_for(directory)
    root = located or requested
    if not is_managed_library(root):
        raise LibraryNotFoundError(f"No managed library at {root}")
    trash = library_dir(root) / LIBRARY_TRASH
    entries: list[dict[str, str]] = []
    if trash.is_dir():
        for path in sorted(trash.rglob("*")):
            if not path.is_file() or not path.name.lower().endswith(ARCHIVE_SUFFIX):
                continue
            relative = path.relative_to(trash).as_posix()
            stamp = relative.split("/", 1)[0]
            inner = relative.split("/", 1)[1] if "/" in relative else ""
            source = inner[: -len(ARCHIVE_SUFFIX)] if inner.lower().endswith(ARCHIVE_SUFFIX) else ""
            stamped = _parse_trash_stamp(stamp)
            entries.append(
                {
                    "entry": relative,
                    "source_path": source,
                    "trashed_at": stamped.isoformat().replace("+00:00", "Z") if stamped else stamp,
                }
            )
    return {"ok": True, "directory": str(root), "entries": entries}


def restore_from_trash(directory: str, entry: str) -> dict[str, Any]:
    """Write the original document back and return its archive to ``.vera/archives``."""
    requested, located = _library_root_for(directory)
    root = located or requested
    if not is_managed_library(root):
        raise LibraryNotFoundError(f"No managed library at {root}")
    relative = entry.replace("\\", "/").strip("/")
    if not relative or any(part in {".", ".."} for part in relative.split("/")):
        raise ValueError(f"Invalid trash entry: {entry}")
    trash = (library_dir(root) / LIBRARY_TRASH).resolve()
    archive = (trash / relative).resolve()
    if not archive.is_relative_to(trash) or not archive.is_file():
        raise FileNotFoundError(entry)
    inner = relative.split("/", 1)[1] if "/" in relative else ""
    if not inner.lower().endswith(ARCHIVE_SUFFIX):
        raise ValueError(f"Invalid trash entry: {entry}")
    source_rel = inner[: -len(ARCHIVE_SUFFIX)]
    destination_source = root / source_rel
    if destination_source.exists():
        raise FileExistsError(f"A document already exists at {source_rel}")
    destination_archive = archive_path_for(root, source_rel)
    with VeraDocument.open(strip_extended_path(archive)) as document:
        export_source_document(document, destination_source)
    destination_archive.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(extended_path(archive), extended_path(destination_archive))
    _remove_empty_parents(archive.parent, trash)
    return {
        "ok": True,
        "directory": str(root),
        "source_path": source_rel,
        "archive": str(destination_archive),
        "restored": str(destination_source),
    }


def _remove_empty_parents(start: Path, stop: Path) -> None:
    current = start
    stop_resolved = stop.resolve()
    while current.resolve() != stop_resolved and current != current.parent:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


__all__ = [
    "LibraryBusyError",
    "LibraryExistsError",
    "LibraryNotFoundError",
    "LibraryUnreachableError",
    "NestedLibraryError",
    "init_library",
    "library_status",
    "list_trash",
    "restore_from_trash",
    "sync_library",
]
