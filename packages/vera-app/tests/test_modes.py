"""Ask/Research mode frontmatter parsing, clamps, and user overrides."""

from __future__ import annotations

from vera_app.modes import load_modes, parse_mode, resolve_mode


def test_parse_mode_clamps_invalid_search_mode_and_numeric_bounds() -> None:
    mode = parse_mode(
        "---\n"
        "name: Custom\n"
        "search_mode: fuzzy\n"
        "top_k: 99\n"
        "context_chunks: -1\n"
        "include_figures: yes\n"
        "max_searches: 0\n"
        "max_chunks: 999\n"
        "max_figure_images: -5\n"
        "---\n"
        "Use the retrieved evidence.\n"
    )
    assert mode is not None
    assert mode.id == "custom"
    assert mode.search_mode == "hybrid"
    assert mode.top_k == 20
    assert mode.context_chunks == 0
    assert mode.include_figures is True
    assert mode.max_searches == 1
    assert mode.max_chunks == 60
    assert mode.max_figure_images == 0
    assert mode.instructions == "Use the retrieved evidence."


def test_parse_mode_coerces_bools_and_intish_floats() -> None:
    mode = parse_mode(
        "---\n"
        "id: figures\n"
        "label: Figures\n"
        "include_figures: 1\n"
        "top_k: 8.9\n"
        "context_chunks: off\n"
        "---\n"
        "Cite figures.\n"
    )
    assert mode is not None
    assert mode.id == "figures"
    assert mode.include_figures is True
    assert mode.top_k == 8
    assert mode.context_chunks == 1


def test_parse_mode_unclosed_frontmatter_and_empty_files() -> None:
    unclosed = parse_mode("---\nname: Broken\nNo closing fence\n")
    assert unclosed is not None
    assert unclosed.instructions.startswith("---")
    assert parse_mode("") is None
    assert parse_mode("   ") is None


def test_parse_mode_slugifies_label_when_id_omitted() -> None:
    mode = parse_mode("# Just a heading\n\nBody text.\n", path="My Mode!.md")
    assert mode is not None
    assert mode.id == "my-mode"
    assert mode.label == "My Mode!"
    assert "Body text." in mode.instructions


def test_user_mode_overrides_builtin_and_unknown_id_falls_back_to_ask(tmp_path) -> None:
    user_dir = tmp_path / "modes"
    user_dir.mkdir()
    (user_dir / "ask.md").write_text(
        "---\n"
        "id: ask\n"
        "name: Ask Local\n"
        "top_k: 2\n"
        "search_mode: keyword\n"
        "---\n"
        "User override instructions.\n",
        encoding="utf-8",
    )
    modes = load_modes(str(user_dir))
    ask = next(mode for mode in modes if mode.id == "ask")
    assert ask.builtin is False
    assert ask.label == "Ask Local"
    assert ask.top_k == 2
    assert ask.search_mode == "keyword"
    assert ask.instructions == "User override instructions."

    resolved = resolve_mode("missing-mode", str(user_dir))
    assert resolved.id == "ask"
    assert resolved.top_k == 2
