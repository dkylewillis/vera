"""Ask mode frontmatter parsing, clamps, and user-override resolution."""

from __future__ import annotations

from vera_app.modes import load_modes, parse_mode, resolve_mode


def test_parse_mode_reads_flat_frontmatter_and_body():
    mode = parse_mode(
        "---\n"
        "name: Ask\n"
        'description: "Grounded answers"\n'
        "search_mode: keyword\n"
        "include_figures: yes\n"
        "---\n"
        "Use only cited evidence.\n",
        path="/tmp/ask.md",
    )
    assert mode is not None
    assert mode.id == "ask"
    assert mode.label == "Ask"
    assert mode.description == "Grounded answers"
    assert mode.search_mode == "keyword"
    assert mode.include_figures is True
    assert mode.instructions == "Use only cited evidence."


def test_parse_mode_strips_bom_and_quoted_scalars():
    mode = parse_mode("\ufeff---\nid: custom-ask\nname: 'Custom Ask'\n---\nBody\n")
    assert mode is not None
    assert mode.id == "custom-ask"
    assert mode.label == "Custom Ask"


def test_parse_mode_without_frontmatter_uses_path_stem():
    mode = parse_mode("Answer from the document.", path="/tmp/notes.md")
    assert mode is not None
    assert mode.id == "notes"
    assert mode.label == "notes"
    assert mode.instructions == "Answer from the document."
    assert mode.search_mode == "hybrid"


def test_parse_mode_returns_none_for_empty_file():
    assert parse_mode("   \n") is None


def test_parse_mode_unclosed_frontmatter_is_treated_as_body():
    mode = parse_mode("---\nname: Broken\nno closing fence\n", path="/tmp/broken.md")
    assert mode is not None
    assert mode.label == "broken"
    assert "name: Broken" in mode.instructions


def test_parse_mode_unknown_search_mode_falls_back_to_hybrid():
    mode = parse_mode("---\nname: Ask\nsearch_mode: fuzzy\n---\nBody\n")
    assert mode is not None
    assert mode.search_mode == "hybrid"


def test_parse_mode_clamps_numeric_guardrails():
    mode = parse_mode(
        "---\n"
        "name: Ask\n"
        "top_k: 99\n"
        "context_chunks: -2\n"
        "max_searches: 0\n"
        "max_chunks: 400\n"
        "max_figure_images: 99\n"
        "---\n"
        "Body\n"
    )
    assert mode is not None
    assert mode.top_k == 20
    assert mode.context_chunks == 0
    assert mode.max_searches == 1
    assert mode.max_chunks == 60
    assert mode.max_figure_images == 20


def test_parse_mode_coerces_bools_and_numeric_strings():
    mode = parse_mode(
        "---\nname: Ask\ninclude_figures: ON\ntop_k: 6.0\ncontext_chunks: bogus\n---\nBody\n"
    )
    assert mode is not None
    assert mode.include_figures is True
    assert mode.top_k == 6
    assert mode.context_chunks == 1


def test_parse_mode_falsey_include_figures():
    mode = parse_mode("---\nname: Ask\ninclude_figures: off\n---\nBody\n")
    assert mode is not None
    assert mode.include_figures is False


def test_load_modes_user_file_overrides_builtin_id(tmp_path):
    user_dir = tmp_path / "modes"
    user_dir.mkdir()
    (user_dir / "ask.md").write_text(
        "---\nname: Ask\nid: ask\ntop_k: 2\n---\nUser instructions.\n",
        encoding="utf-8",
    )
    modes = {mode.id: mode for mode in load_modes(str(user_dir))}
    assert modes["ask"].builtin is False
    assert modes["ask"].top_k == 2
    assert modes["ask"].instructions == "User instructions."
    assert "research" in modes
    assert modes["research"].builtin is True


def test_resolve_mode_falls_back_to_ask():
    ask = resolve_mode(None)
    assert ask.id == "ask"
    unknown = resolve_mode("does-not-exist")
    assert unknown.id == "ask"


def test_resolve_mode_selects_user_id(tmp_path):
    user_dir = tmp_path / "modes"
    user_dir.mkdir()
    (user_dir / "figures.md").write_text(
        "---\nname: Figures\ninclude_figures: true\n---\nUse figures.\n",
        encoding="utf-8",
    )
    mode = resolve_mode("figures", str(user_dir))
    assert mode.id == "figures"
    assert mode.include_figures is True
