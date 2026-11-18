"""Plugin folders: pure-Python ingest pipeline wheels unpacked outside site-packages.

A plugin root holds one subfolder per installed plugin, each the unpacked
contents of a ``py3-none-any`` wheel (its package plus ``*.dist-info``).
``VERA_PLUGIN_DIRS`` lists plugin roots separated by :data:`os.pathsep`.
Pipeline discovery appends every plugin folder to ``sys.path`` first, so the
plugin's ``vera.ingest_pipelines`` entry points are found the same way as a
``pip install``. Plugin folders go last on ``sys.path``: a module the host
already ships always wins over a copy inside a plugin.
"""

from __future__ import annotations

import configparser
import importlib
import importlib.metadata
import importlib.util
import os
import re
import shutil
import sys
import uuid
import zipfile
from email.parser import Parser
from pathlib import Path, PurePosixPath
from typing import Any

PLUGIN_DIRS_ENV = "VERA_PLUGIN_DIRS"
PIPELINE_ENTRY_POINT_GROUP = "vera.ingest_pipelines"

__all__ = [
    "PLUGIN_DIRS_ENV",
    "activate_plugin_dirs",
    "install_plugin_wheel",
    "list_plugins",
    "plugin_roots",
    "remove_plugin",
]


def plugin_roots() -> list[Path]:
    """Plugin roots named by ``VERA_PLUGIN_DIRS``, in order."""
    raw = os.environ.get(PLUGIN_DIRS_ENV, "")
    return [Path(part).expanduser() for part in raw.split(os.pathsep) if part.strip()]


def _plugin_folders(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(
        child for child in root.iterdir() if child.is_dir() and not child.name.startswith(".")
    )


def activate_plugin_dirs(roots: list[Path] | None = None) -> list[str]:
    """Append each installed plugin folder to ``sys.path``; return the folders added."""
    added: list[str] = []
    for root in plugin_roots() if roots is None else roots:
        for folder in _plugin_folders(Path(root)):
            entry = str(folder)
            if entry not in sys.path:
                sys.path.append(entry)
                added.append(entry)
    if added:
        importlib.invalidate_caches()
    return added


def _normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).strip("-").lower()


def _dist_info(folder: Path) -> importlib.metadata.Distribution | None:
    for candidate in sorted(folder.glob("*.dist-info")):
        if (candidate / "METADATA").is_file():
            return importlib.metadata.Distribution.at(candidate)
    return None


def _describe(folder: Path) -> dict[str, Any]:
    dist = _dist_info(folder)
    if dist is None:
        return {
            "name": folder.name,
            "version": "",
            "summary": "",
            "path": str(folder),
            "pipelines": [],
            "error": "No .dist-info metadata in this plugin folder.",
        }
    pipelines = sorted(
        entry.name.strip().lower()
        for entry in dist.entry_points
        if entry.group == PIPELINE_ENTRY_POINT_GROUP and entry.name.strip()
    )
    return {
        "name": dist.metadata.get("Name") or folder.name,
        "version": dist.version or "",
        "summary": dist.metadata.get("Summary") or "",
        "path": str(folder),
        "pipelines": pipelines,
    }


def list_plugins(root: str | Path) -> list[dict[str, Any]]:
    """Describe each plugin installed under ``root``."""
    return [_describe(folder) for folder in _plugin_folders(Path(root))]


def _read_wheel_member(archive: zipfile.ZipFile, name: str) -> str:
    try:
        return archive.read(name).decode("utf-8")
    except KeyError:
        return ""


def _wheel_dist_info(archive: zipfile.ZipFile) -> str:
    folders = {
        PurePosixPath(name).parts[0]
        for name in archive.namelist()
        if PurePosixPath(name).parts and PurePosixPath(name).parts[0].endswith(".dist-info")
    }
    with_metadata = [folder for folder in folders if f"{folder}/METADATA" in archive.namelist()]
    if len(with_metadata) != 1:
        raise ValueError("This file is not a Python wheel: it needs exactly one .dist-info folder.")
    return with_metadata[0]


def _check_pure(wheel_text: str, name: str) -> None:
    fields = Parser().parsestr(wheel_text)
    tags = [tag.strip() for tag in fields.get_all("Tag") or []]
    purelib = (fields.get("Root-Is-Purelib") or "").strip().lower() == "true"
    if not purelib or not tags or not all(tag.endswith("-none-any") for tag in tags):
        built_for = ", ".join(tags) or "an unknown platform"
        raise ValueError(
            f"{name} is built for {built_for}. Only pure-Python plugins "
            "(py3-none-any wheels) can be installed."
        )


def _pipeline_entry_points(entry_points_text: str) -> list[str]:
    parser = configparser.ConfigParser(delimiters=("=",), interpolation=None)
    parser.optionxform = str  # type: ignore[assignment,method-assign]
    parser.read_string(entry_points_text)
    if not parser.has_section(PIPELINE_ENTRY_POINT_GROUP):
        return []
    return sorted(key.strip().lower() for key in parser[PIPELINE_ENTRY_POINT_GROUP] if key.strip())


def _requirement_available(requirement: str) -> bool:
    match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", requirement)
    if not match:
        return True
    name = match.group(1)
    try:
        importlib.metadata.distribution(name)
        return True
    except importlib.metadata.PackageNotFoundError:
        pass
    try:
        return importlib.util.find_spec(name.replace("-", "_")) is not None
    except (ImportError, ValueError):
        return False


def _missing_requirements(metadata: Any) -> list[str]:
    missing = []
    for requirement in metadata.get_all("Requires-Dist") or []:
        _spec, _sep, marker = requirement.partition(";")
        if "extra" in marker:
            continue
        if not _requirement_available(requirement):
            missing.append(requirement.strip())
    return missing


def _target_path(member: str, data_dir: str) -> PurePosixPath | None:
    path = PurePosixPath(member)
    if path.is_absolute() or ".." in path.parts or not path.parts or ":" in path.parts[0]:
        raise ValueError(f"Wheel entry {member!r} points outside the plugin folder.")
    if path.parts[0] == data_dir:
        # Only importable code from <name>.data/ belongs on sys.path.
        if len(path.parts) > 2 and path.parts[1] in {"purelib", "platlib"}:
            return PurePosixPath(*path.parts[2:])
        return None
    return path


def install_plugin_wheel(wheel_path: str | Path, root: str | Path) -> dict[str, Any]:
    """Unpack a pure-Python plugin wheel into ``root/<name>``, replacing an older copy.

    The new pipelines are visible to processes that start after this call.
    Returns the installed plugin's description plus ``warnings`` (missing
    requirements, provider names already taken by an installed pipeline).
    """
    from .pipeline import list_ingest_pipelines

    wheel = Path(wheel_path)
    if wheel.suffix.lower() != ".whl" or not wheel.is_file():
        raise ValueError(f"Choose a .whl plugin file (got {wheel.name or wheel}).")
    if not zipfile.is_zipfile(wheel):
        raise ValueError(f"{wheel.name} is not a valid wheel archive.")
    plugins_root = Path(root)
    with zipfile.ZipFile(wheel) as archive:
        dist_info = _wheel_dist_info(archive)
        metadata = Parser().parsestr(_read_wheel_member(archive, f"{dist_info}/METADATA"))
        display_name = (metadata.get("Name") or "").strip()
        if not display_name:
            raise ValueError(f"{wheel.name} has no project name in its metadata.")
        _check_pure(_read_wheel_member(archive, f"{dist_info}/WHEEL"), display_name)
        pipelines = _pipeline_entry_points(
            _read_wheel_member(archive, f"{dist_info}/entry_points.txt")
        )
        if not pipelines:
            raise ValueError(
                f"{display_name} does not register a VERA ingest pipeline "
                f"(no {PIPELINE_ENTRY_POINT_GROUP} entry point)."
            )
        warnings = [
            f"Needs {requirement}, which this VERA does not include; the plugin may fail to load."
            for requirement in _missing_requirements(metadata)
        ]
        name = _normalize_name(display_name)
        target = plugins_root / name
        # Reinstalling over an older copy: its own providers are not a conflict.
        taken = set() if target.is_dir() else set(list_ingest_pipelines())
        warnings.extend(
            f"A pipeline named '{provider}' is already installed, so this plugin's "
            f"'{provider}' will be ignored."
            for provider in pipelines
            if provider in taken
        )
        data_dir = dist_info[: -len(".dist-info")] + ".data"
        plugins_root.mkdir(parents=True, exist_ok=True)
        staging = plugins_root / f".install-{name}-{uuid.uuid4().hex[:8]}"
        staging.mkdir()
        try:
            for info in archive.infolist():
                relative = _target_path(info.filename, data_dir)
                if relative is None or info.is_dir():
                    continue
                destination = staging.joinpath(*relative.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, destination.open("wb") as sink:
                    shutil.copyfileobj(source, sink)
            if target.exists():
                retired = plugins_root / f".remove-{name}-{uuid.uuid4().hex[:8]}"
                target.rename(retired)
                shutil.rmtree(retired, ignore_errors=True)
            staging.rename(target)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
    return {**_describe(target), "warnings": warnings}


def remove_plugin(name: str, root: str | Path) -> dict[str, Any]:
    """Delete the plugin folder ``root/<name>``."""
    plugins_root = Path(root).resolve()
    folder_name = _normalize_name(name)
    target = (plugins_root / folder_name).resolve()
    if not folder_name or target.parent != plugins_root or not target.is_dir():
        raise ValueError(f"No plugin named {name!r} is installed.")
    shutil.rmtree(target)
    return {"name": folder_name, "removed": True}
