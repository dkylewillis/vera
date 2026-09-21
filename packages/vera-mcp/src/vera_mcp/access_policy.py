"""Fail-closed access policy for the Desktop bridge MCP launch mode.

Ordinary local ``vera mcp`` runs without a policy. Bridge mode requires an
explicit policy loaded from ``VERA_BRIDGE_POLICY_PATH`` and checks every archive
open, corpus root, indexed locator, and viewer navigation path.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any

POLICY_ENV = "VERA_BRIDGE_POLICY_PATH"
DEFAULT_MAX_TOP_K = 20
DEFAULT_MAX_CONTEXT_CHUNKS = 2
DEFAULT_MAX_SOURCES = 12
BRIDGE_TOOLS = frozenset(
    {
        "vera_library_info",
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


class AccessDenied(PermissionError):
    """Raised when a bridge path or bound is outside the approved policy."""

    def __init__(self, message: str = "Access denied by VERA bridge policy.") -> None:
        super().__init__(message)


@dataclass(frozen=True)
class AccessPolicy:
    """Approved local library grant for a restricted MCP process."""

    library_root: Path
    max_top_k: int = DEFAULT_MAX_TOP_K
    max_context_chunks: int = DEFAULT_MAX_CONTEXT_CHUNKS
    max_sources: int = DEFAULT_MAX_SOURCES
    allowed_tools: frozenset[str] = BRIDGE_TOOLS

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> AccessPolicy:
        if not isinstance(data, dict) or not data:
            raise ValueError("Bridge policy is empty or invalid (library_root required).")
        raw_root = data.get("library_root")
        if not isinstance(raw_root, str) or not raw_root.strip():
            raise ValueError("Bridge policy requires a non-empty library_root.")
        root = canonicalize_path(raw_root, require_directory=True)
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
        return cls(
            library_root=root,
            max_top_k=max_top_k,
            max_context_chunks=max_context_chunks,
            max_sources=max_sources,
            allowed_tools=allowed,
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
        return {
            "library_root": str(self.library_root),
            "supported_modes": ["hybrid", "semantic", "keyword"],
            "max_top_k": self.max_top_k,
            "max_context_chunks": self.max_context_chunks,
            "max_sources": self.max_sources,
            "tools": sorted(self.allowed_tools),
            "disclosure": (
                "Your library stays on your computer. Requested excerpts and source "
                "previews are shared with ChatGPT. Absolute archive paths are visible "
                "to the host in this PoC."
            ),
        }

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

    def check_library_root(self, directory: str | Path) -> Path:
        path = canonicalize_path(directory, require_directory=True)
        if path != self.library_root and not _is_relative_to(path, self.library_root):
            raise AccessDenied()
        return path

    def check_archive(self, file: str | Path) -> Path:
        path = canonicalize_path(file, require_directory=False)
        if path.suffix.lower() != ".vera":
            raise AccessDenied("Only .vera archives are allowed.")
        if not _is_relative_to(path, self.library_root):
            raise AccessDenied()
        if not path.is_file():
            raise AccessDenied("Archive was not found in the approved library.")
        return path


def load_policy_from_env() -> AccessPolicy:
    """Load the bridge policy path from ``VERA_BRIDGE_POLICY_PATH`` (fail closed)."""
    raw = (os.environ.get(POLICY_ENV) or "").strip()
    if not raw:
        raise ValueError(f"Bridge mode requires {POLICY_ENV} pointing at a policy JSON file.")
    return AccessPolicy.load(raw)


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
