"""Tool-table budgets, allowlists, and events."""

from __future__ import annotations

from vera_app.agent_tools import AgentTool, ToolContext, ToolTable, allowlisted
from vera_app.citations import CitationRegistry
from vera_app.modes import Mode, parse_mode


def _ctx() -> tuple[ToolContext, list[dict]]:
    events: list[dict] = []
    ctx = ToolContext(
        request={"path": "manual.vera"},
        mode=Mode(id="ask", label="Ask", max_searches=2),
        citations=CitationRegistry(),
        write_event=events.append,
    )
    return ctx, events


def test_tool_table_enforces_budget_and_emits_events() -> None:
    def run(arguments, ctx):
        ctx.outputs.setdefault("notes", []).append(arguments["value"])
        return {"ok": True}

    tool = AgentTool(
        name="note",
        schema={"type": "function", "function": {"name": "note"}},
        run=run,
        max_calls=1,
    )
    table = ToolTable([tool])
    ctx, events = _ctx()
    assert table.dispatch("note", {"value": "a"}, ctx) == {"ok": True}
    assert table.dispatch("note", {"value": "b"}, ctx)["error"].startswith("Tool budget")
    assert table.dispatch("missing", {}, ctx)["error"].startswith("Unknown tool")
    assert ctx.outputs["notes"] == ["a"]
    assert [event["event"] for event in events] == ["tool_start", "tool_done"]
    assert table.offered(ctx) == []
    assert table.max_turns() == 2


def test_unavailable_tools_are_not_offered() -> None:
    tool = AgentTool(
        name="search",
        schema={"type": "function", "function": {"name": "search"}},
        run=lambda arguments, ctx: {},
        max_calls=3,
        available=lambda ctx: bool(ctx.request.get("path")),
    )
    table = ToolTable([tool])
    ctx, _events = _ctx()
    assert table.offered(ctx) == [tool]
    ctx.request = {}
    assert table.offered(ctx) == []
    assert table.offered(ctx, force_answer=True) == []


def test_mode_allowlist_drops_unlisted_tools() -> None:
    search = AgentTool("search", {}, lambda a, c: {}, max_calls=1)
    writer = AgentTool("write_markdown", {}, lambda a, c: {}, max_calls=1)
    mode = parse_mode("---\nid: ask\ntools: search\nsearch_policy: always\n---\nBody\n")
    assert mode is not None
    assert mode.search_policy == "always"
    assert [tool.name for tool in allowlisted([search, writer], mode)] == ["search"]
    open_mode = parse_mode("---\nid: ask\n---\nBody\n")
    assert open_mode is not None
    assert [tool.name for tool in allowlisted([search, writer], open_mode)] == ["search", "write_markdown"]
