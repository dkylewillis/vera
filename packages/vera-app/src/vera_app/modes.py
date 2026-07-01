"""Answer modes loaded from markdown files (frontmatter + instruction body).

A mode bundles the system instructions (the markdown body) with retrieval
defaults and agent-loop guardrails (the YAML-ish frontmatter). Built-in modes
ship inside this package; users can add or override modes by dropping ``.md``
files into a user modes directory (user files win on name collisions).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

BUILTIN_DIR = Path(__file__).resolve().parent / "modes_builtin"

_TRUE = {"true", "yes", "on", "1"}
_FALSE = {"false", "no", "off", "0"}
_SEARCH_MODES = {"hybrid", "semantic", "keyword"}


@dataclass(frozen=True)
class Mode:
    id: str
    label: str
    description: str = ""
    instructions: str = ""
    search_mode: str = "hybrid"
    top_k: int = 8
    context_chunks: int = 1
    include_figures: bool = False
    max_searches: int = 6
    max_chunks: int = 20
    max_figure_images: int = 4
    builtin: bool = False
    path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "instructions": self.instructions,
            "search_mode": self.search_mode,
            "top_k": self.top_k,
            "context_chunks": self.context_chunks,
            "include_figures": self.include_figures,
            "max_searches": self.max_searches,
            "max_chunks": self.max_chunks,
            "max_figure_images": self.max_figure_images,
            "builtin": self.builtin,
            "path": self.path,
        }


def _coerce_bool(value: str, default: bool) -> bool:
    token = value.strip().lower()
    if token in _TRUE:
        return True
    if token in _FALSE:
        return False
    return default


def _coerce_int(value: str, default: int) -> int:
    try:
        return int(float(value.strip()))
    except (TypeError, ValueError):
        return default


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split a markdown file into a flat frontmatter mapping and a body.

    Only flat ``key: value`` scalar frontmatter is supported, which is all a
    mode needs. Anything more complex is treated as part of the body.
    """
    stripped = text.lstrip("\ufeff")
    if not stripped.startswith("---"):
        return {}, text.strip()
    lines = stripped.splitlines()
    # Drop the opening fence (line 0 == '---').
    closing = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            closing = index
            break
    if closing is None:
        return {}, text.strip()
    meta: dict[str, str] = {}
    for line in lines[1:closing]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        meta[key.strip().lower()] = value.strip().strip('"').strip("'")
    body = "\n".join(lines[closing + 1:]).strip()
    return meta, body


def _slugify(name: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in name)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "mode"


def parse_mode(text: str, *, path: str = "", builtin: bool = False) -> Mode | None:
    meta, body = _parse_frontmatter(text)
    label = meta.get("name") or meta.get("label") or (Path(path).stem if path else "")
    if not label and not body:
        return None
    mode_id = meta.get("id") or _slugify(label or Path(path).stem or "mode")
    search_mode = meta.get("search_mode", "hybrid").strip().lower()
    if search_mode not in _SEARCH_MODES:
        search_mode = "hybrid"
    return Mode(
        id=mode_id,
        label=label or mode_id,
        description=meta.get("description", ""),
        instructions=body,
        search_mode=search_mode,
        top_k=max(1, min(20, _coerce_int(meta.get("top_k", "8"), 8))),
        context_chunks=max(0, min(3, _coerce_int(meta.get("context_chunks", "1"), 1))),
        include_figures=_coerce_bool(meta.get("include_figures", "false"), False),
        max_searches=max(1, min(12, _coerce_int(meta.get("max_searches", "6"), 6))),
        max_chunks=max(1, min(60, _coerce_int(meta.get("max_chunks", "20"), 20))),
        max_figure_images=max(0, min(20, _coerce_int(meta.get("max_figure_images", "4"), 4))),
        builtin=builtin,
        path=path,
    )


def _load_dir(directory: Path, *, builtin: bool) -> list[Mode]:
    modes: list[Mode] = []
    if not directory.is_dir():
        return modes
    for file in sorted(directory.glob("*.md")):
        try:
            mode = parse_mode(file.read_text(encoding="utf-8"), path=str(file), builtin=builtin)
        except OSError:
            continue
        if mode is not None:
            modes.append(mode)
    return modes


def load_modes(user_dir: str | None = None) -> list[Mode]:
    """Return built-in modes plus user modes; user files override by id."""
    by_id: dict[str, Mode] = {}
    for mode in _load_dir(BUILTIN_DIR, builtin=True):
        by_id[mode.id] = mode
    if user_dir:
        for mode in _load_dir(Path(user_dir), builtin=False):
            by_id[mode.id] = mode
    return list(by_id.values())


def resolve_mode(mode_id: str | None, user_dir: str | None = None) -> Mode:
    modes = load_modes(user_dir)
    if not modes:
        return Mode(id="ask", label="Ask")
    if mode_id:
        for mode in modes:
            if mode.id == mode_id:
                return mode
    for mode in modes:
        if mode.id == "ask":
            return mode
    return modes[0]
