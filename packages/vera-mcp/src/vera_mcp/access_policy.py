"""Fail-closed access policy for restricted VERA MCP launch modes.

Ordinary local ``vera mcp`` runs without a policy. The Desktop agent service
requires an explicit policy and checks every archive open, corpus root,
indexed locator, and viewer navigation path. A policy may approve several
library folders. Each folder has a short name agents can pass instead of a
path. The legacy single ``library_root`` key is still accepted.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any

DEFAULT_MAX_TOP_K = 20
DEFAULT_MAX_CONTEXT_CHUNKS = 2
DEFAULT_MAX_SOURCES = 12
_LIBRARY_NAME_MAX = 64
_LIBRARY_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_LIBRARY_NAME_HELP = (
    "Bridge policy library name must be a lowercase slug of at most 64 characters "
    "(letters, numbers, hyphens, underscores)."
)
BRIDGE_TOOLS = frozenset(
    {
        "vera_library_info",
        "vera_library_status",
        "vera_search",
        "vera_corpus_search",
        "vera_inspect",
        "vera_figures",
        "vera_get_figure",
        "vera_get_page",
        "vera_get_chunk",
        "vera_get_chunk_regions",
        "vera_show_sources",
        "vera_source_page",
    }
)

LOCAL_AGENT_DISCLOSURE = (
    "Your library stays on your computer. Requested excerpts and source "
    "previews are returned to the local agent that asked for them, and that "
    "agent's model provider receives them."
)


class AccessDenied(PermissionError):
    """Raised when a bridge path or bound is outside the approved policy."""

    def __init__(self, message: str = "Access denied by VERA bridge policy.") -> None:
        super().__init__(message)


@dataclass(frozen=True)
class AccessPolicy:
    """Approved local library grant for a restricted MCP process."""

    library_roots: tuple[Path, ...]
    max_top_k: int = DEFAULT_MAX_TOP_K
    max_context_chunks: int = DEFAULT_MAX_CONTEXT_CHUNKS
    max_sources: int = DEFAULT_MAX_SOURCES
    allowed_tools: frozenset[str] = BRIDGE_TOOLS
    disclosure: str = LOCAL_AGENT_DISCLOSURE
    computer: tuple[str, str] | None = None
    library_names: tuple[tuple[Path, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.library_roots:
            raise ValueError("Bridge policy requires at least one library root.")
        roots = _collapse_roots(self.library_roots)
        object.__setattr__(self, "library_roots", roots)
        explicit: dict[Path, str] = {}
        for path, name in self.library_names:
            if not isinstance(name, str) or _LIBRARY_NAME_RE.fullmatch(name) is None:
                raise ValueError(_LIBRARY_NAME_HELP)
            matched = next((root for root in roots if root == path), None)
            if matched is None:
                continue
            if matched in explicit and explicit[matched] != name:
                raise ValueError(
                    f"Bridge policy library name for {matched} is listed more than once."
                )
            explicit[matched] = name
        object.__setattr__(self, "library_names", _assign_library_names(roots, explicit))
        if self.computer is not None:
            ident, name = self.computer
            if not isinstance(ident, str) or not ident.strip() or len(ident.strip()) > 64:
                raise ValueError("Bridge policy computer id must be a non-empty string of at most 64 characters.")
            if not isinstance(name, str) or not name.strip() or len(name.strip()) > 64:
                raise ValueError("Bridge policy computer name must be a non-empty string of at most 64 characters.")
            object.__setattr__(self, "computer", (ident.strip(), name.strip()))

    @property
    def library_root(self) -> Path:
        """The only approved root. Raises when the policy approves more than one."""
        if len(self.library_roots) != 1:
            raise ValueError("library_root is only available when the policy has one root.")
        return self.library_roots[0]

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> AccessPolicy:
        if not isinstance(data, dict) or not data:
            raise ValueError("Bridge policy is empty or invalid (library_root required).")
        roots = _roots_from_mapping(data)
        max_top_k = _positive_int(data.get("max_top_k", DEFAULT_MAX_TOP_K), "max_top_k")
        max_context_chunks = _non_negative_int(
            data.get("max_context_chunks", DEFAULT_MAX_CONTEXT_CHUNKS),
            "max_context_chunks",
        )
        max_sources = _positive_int(data.get("max_sources", DEFAULT_MAX_SOURCES), "max_sources")
        tools = data.get("allowed_tools")
        if tools is None:
            allowed = BRIDGE_TOOLS
        else:
            if not isinstance(tools, list) or not tools:
                raise ValueError("Bridge policy allowed_tools must be a non-empty list.")
            allowed = frozenset(str(item) for item in tools)
            unknown = allowed - BRIDGE_TOOLS
            if unknown:
                raise ValueError(f"Bridge policy lists unsupported tools: {sorted(unknown)}")
        disclosure = data.get("disclosure", LOCAL_AGENT_DISCLOSURE)
        if not isinstance(disclosure, str) or not disclosure.strip():
            raise ValueError("Bridge policy disclosure must be a non-empty string.")
        return cls(
            library_roots=roots,
            max_top_k=max_top_k,
            max_context_chunks=max_context_chunks,
            max_sources=max_sources,
            allowed_tools=allowed,
            disclosure=disclosure.strip(),
            computer=_computer_from_mapping(data.get("computer", None)),
            library_names=_library_names_from_mapping(data),
        )

    @classmethod
    def load(cls, path: str | Path) -> AccessPolicy:
        policy_path = Path(path)
        if not policy_path.is_file():
            raise ValueError("Bridge policy file is missing or not a regular file.")
        try:
            raw = json.loads(policy_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("Bridge policy file could not be read as JSON.") from exc
        if not isinstance(raw, dict):
            raise ValueError("Bridge policy root must be a JSON object.")
        return cls.from_mapping(raw)

    def discovery(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "library_roots": [str(root) for root in self.library_roots],
            "libraries": [{"name": name, "path": str(root)} for root, name in self.library_names],
            "supported_modes": ["hybrid", "semantic", "keyword"],
            "max_top_k": self.max_top_k,
            "max_context_chunks": self.max_context_chunks,
            "max_sources": self.max_sources,
            "tools": sorted(self.allowed_tools),
            "disclosure": self.disclosure,
        }
        if len(self.library_roots) == 1:
            payload["library_root"] = str(self.library_roots[0])
        if self.computer is not None:
            payload["computer"] = {"id": self.computer[0], "name": self.computer[1]}
        return payload

    def clamp_top_k(self, top_k: int) -> int:
        value = int(top_k)
        if value < 1:
            raise AccessDenied("top_k must be at least 1.")
        return min(value, self.max_top_k)

    def clamp_context_chunks(self, context_chunks: int) -> int:
        value = int(context_chunks)
        if value < 0:
            raise AccessDenied("context_chunks must be non-negative.")
        return min(value, self.max_context_chunks)

    def require_tool(self, name: str) -> None:
        if name not in self.allowed_tools:
            raise AccessDenied("Tool is not enabled for the VERA bridge.")

    def contains(self, path: Path) -> bool:
        return any(path == root or _is_relative_to(path, root) for root in self.library_roots)

    def check_library_root(self, directory: str | Path) -> Path:
        path = canonicalize_path(directory, require_directory=True)
        if not self.contains(path):
            raise AccessDenied(self.outside_roots_message())
        return path

    def check_archive(self, file: str | Path) -> Path:
        path = canonicalize_path(file, require_directory=False)
        if path.suffix.lower() != ".vera":
            raise AccessDenied("Only .vera archives are allowed.")
        if not self.contains(path):
            raise AccessDenied(self.outside_roots_message())
        if not path.is_file():
            raise AccessDenied("Archive was not found in the approved library.")
        return path

    def resolve_library(self, name: str) -> Path:
        """Return the approved folder for a library name. Matching ignores case."""
        key = name.strip().lower() if isinstance(name, str) else ""
        if not key:
            raise AccessDenied(self._unknown_library_message(name))
        matches = [root for root, library_name in self.library_names if library_name == key]
        if len(matches) != 1:
            raise AccessDenied(self._unknown_library_message(name))
        return matches[0]

    def resolve(self, library: str | None, relative: str | Path | None, *, directory: bool) -> Path:
        """Resolve a tool path, then apply the existing root and archive checks.

        A call passes either an absolute path with no library, or a library name
        plus a path relative to that library. An empty relative directory means
        the library folder itself.
        """
        library_name = library.strip() if isinstance(library, str) else ""
        text = "" if relative is None else str(relative).strip()
        if not library_name:
            if not text:
                raise AccessDenied("Path is empty.")
            if directory:
                return self.check_library_root(text)
            return self.check_archive(text)
        if not text:
            if not directory:
                raise AccessDenied("Archive path is required.")
            return self.check_library_root(self.resolve_library(library_name))
        _reject_library_relative(text)
        root = self.resolve_library(library_name)
        joined = root / text
        if directory:
            return self.check_library_root(joined)
        return self.check_archive(joined)

    def _unknown_library_message(self, name: object) -> str:
        listed = ", ".join(library_name for _, library_name in self.library_names)
        shown = name.strip() if isinstance(name, str) else name
        return f"Unknown library {shown!r}. Approved libraries: {listed}."

    def outside_roots_message(self) -> str:
        if self.computer is None:
            return "Access denied by VERA bridge policy."
        name = self.computer[1]
        return (
            f"This path is not in the approved libraries on {name}. "
            "Call vera_library_info; the user may have switched computers."
        )


def library_slug(text: str) -> str:
    """Normalize a folder name into a library slug. Empty when no slug fits.

    The desktop app copies this rule in ``library-names.ts``. Keep the two together.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    slug = slug[:_LIBRARY_NAME_MAX].rstrip("-")
    if _LIBRARY_NAME_RE.fullmatch(slug):
        return slug
    return ""


def _disambiguated_library_name(root: Path, base: str) -> str:
    parent = library_slug(root.parent.name)
    if not parent or not base:
        raise ValueError(
            f"Bridge policy library name {base!r} is not unique "
            f"and could not be disambiguated for {root}."
        )
    candidate = f"{parent}-{base}"
    if len(candidate) > _LIBRARY_NAME_MAX:
        candidate = candidate[:_LIBRARY_NAME_MAX].rstrip("-")
    if _LIBRARY_NAME_RE.fullmatch(candidate) is None:
        raise ValueError(
            f"Bridge policy library name {base!r} is not unique "
            f"and could not be disambiguated for {root}."
        )
    return candidate


def _assign_library_names(
    roots: tuple[Path, ...], explicit: dict[Path, str]
) -> tuple[tuple[Path, str], ...]:
    """Apply explicit names, then unique fallbacks from folder names."""
    assigned: dict[Path, str] = {}
    used: dict[str, Path] = {}
    for root in roots:
        if root not in explicit:
            continue
        name = explicit[root]
        if name in used:
            raise ValueError(f"Bridge policy library name {name!r} is used more than once.")
        assigned[root] = name
        used[name] = root
    bases: list[tuple[Path, str]] = []
    for root in roots:
        if root in assigned:
            continue
        base = library_slug(root.name)
        if not base:
            raise ValueError(f"Bridge policy could not derive a library name for {root}.")
        bases.append((root, base))
    counts = Counter(base for _, base in bases)
    for root, base in bases:
        if counts[base] == 1 and base not in used:
            name = base
        else:
            name = _disambiguated_library_name(root, base)
        if name in used:
            raise ValueError(f"Bridge policy library name {name!r} is used more than once.")
        assigned[root] = name
        used[name] = root
    return tuple((root, assigned[root]) for root in roots)


def _library_names_from_mapping(data: dict[str, Any]) -> tuple[tuple[Path, str], ...]:
    raw = data.get("library_names", {})
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("Bridge policy library_names must be an object.")
    pairs: list[tuple[Path, str]] = []
    for key, name in raw.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("Bridge policy library_names keys must be non-empty strings.")
        if not isinstance(name, str) or _LIBRARY_NAME_RE.fullmatch(name) is None:
            raise ValueError(_LIBRARY_NAME_HELP)
        try:
            canonical = canonicalize_path(key, require_directory=True)
        except AccessDenied as exc:
            raise ValueError(
                f"Bridge policy library_names key is not a library folder: {key}"
            ) from exc
        pairs.append((canonical, name))
    return tuple(pairs)


def _reject_library_relative(text: str) -> None:
    absolute = text.startswith(("/", "\\")) or (
        len(text) >= 2 and text[0].isalpha() and text[1] == ":"
    )
    if absolute or Path(text).is_absolute():
        raise AccessDenied(
            "Pass a path relative to the named library, or omit library and pass an absolute path."
        )
    if any(part == ".." for part in re.split(r"[\\/]", text)):
        raise AccessDenied("Library paths must stay inside the named library.")


def _computer_from_mapping(raw: Any) -> tuple[str, str] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("Bridge policy computer must be an object with id and name.")
    ident = raw.get("id")
    name = raw.get("name")
    if not isinstance(ident, str) or not isinstance(name, str):
        raise ValueError("Bridge policy computer id and name must be strings.")
    return (ident, name)


def _roots_from_mapping(data: dict[str, Any]) -> tuple[Path, ...]:
    raw_roots = data.get("library_roots")
    raw_root = data.get("library_root")
    texts: list[str] = []
    if raw_roots is not None:
        if not isinstance(raw_roots, list) or not raw_roots:
            raise ValueError("Bridge policy library_roots must be a non-empty list.")
        for item in raw_roots:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("Bridge policy library_roots entries must be non-empty strings.")
            texts.append(item)
    if raw_root is not None:
        if not isinstance(raw_root, str) or not raw_root.strip():
            raise ValueError("Bridge policy requires a non-empty library_root.")
        texts.append(raw_root)
    if not texts:
        raise ValueError("Bridge policy requires a non-empty library_root.")
    return tuple(canonicalize_path(item, require_directory=True) for item in texts)


def _collapse_roots(roots: tuple[Path, ...] | list[Path]) -> tuple[Path, ...]:
    """Drop duplicates and roots nested inside another approved root."""
    kept: list[Path] = []
    for root in roots:
        if any(root == existing or _is_relative_to(root, existing) for existing in kept):
            continue
        kept = [existing for existing in kept if not _is_relative_to(existing, root)]
        kept.append(root)
    return tuple(kept)


def canonicalize_path(value: str | Path, *, require_directory: bool) -> Path:
    """Resolve a local path and reject UNC, device, and reparse escapes."""
    text = str(value).strip()
    if not text:
        raise AccessDenied("Path is empty.")
    if _is_unc_or_device(text):
        raise AccessDenied("Network and device paths are not allowed.")
    path = Path(text)
    if not path.is_absolute():
        raise AccessDenied("Use an absolute path.")
    try:
        resolved = path.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise AccessDenied("Path could not be resolved.") from exc
    try:
        real = Path(os.path.realpath(resolved))
    except (OSError, RuntimeError) as exc:
        raise AccessDenied("Path could not be resolved.") from exc
    if _is_unc_or_device(str(real)):
        raise AccessDenied("Network and device paths are not allowed.")
    if require_directory:
        if not real.is_dir():
            raise AccessDenied("Approved library root must be an existing directory.")
    return real


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _is_unc_or_device(text: str) -> bool:
    if text.startswith("\\\\?\\UNC\\") or text.startswith("//?/UNC/"):
        return True
    if text.startswith("\\\\.\\") or text.startswith("//./"):
        return True
    # Classic UNC: \\server\share\...
    if text.startswith("\\\\") or text.startswith("//"):
        # Allow extended-length local paths \\?\C:\...
        rest = text[2:]
        if rest.startswith("?\\") or rest.startswith("?/"):
            drive = rest[2:4]
            return not (len(drive) == 2 and drive[1] == ":" and drive[0].isalpha())
        return True
    if sys.platform == "win32":
        pure = PureWindowsPath(text)
        if pure.drive.upper().startswith("\\\\") or pure.anchor.startswith("\\\\"):
            return True
    return False


def _positive_int(value: Any, name: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Bridge policy {name} must be an integer.") from exc
    if number < 1:
        raise ValueError(f"Bridge policy {name} must be at least 1.")
    return number


def _non_negative_int(value: Any, name: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Bridge policy {name} must be an integer.") from exc
    if number < 0:
        raise ValueError(f"Bridge policy {name} must be non-negative.")
    return number
