"""Small tool table for the Ask agent loop.

Each tool has a schema, a handler, a per-answer call budget, and a predicate
that says whether it applies to this request. The loop offers only the tools
that still have budget and currently apply.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from vera_app.cancellation import CancellationToken
from vera_app.citations import CitationRegistry
from vera_app.modes import Mode
from vera_app.types import Request, WriteEvent

ToolHandler = Callable[[dict[str, Any], "ToolContext"], dict[str, Any]]
Availability = Callable[["ToolContext"], bool]


@dataclass
class ToolContext:
    """Shared state for every tool call in one answer."""

    request: Request
    mode: Mode
    citations: CitationRegistry
    write_event: WriteEvent | None = None
    cancel: CancellationToken | None = None
    outputs: dict[str, Any] = field(default_factory=dict)
    vision_available: bool = True
    calls: dict[str, int] = field(default_factory=dict)
    search_tool: Any = None


@dataclass
class AgentTool:
    """One callable the model may invoke."""

    name: str
    schema: dict[str, Any]
    run: ToolHandler
    max_calls: int
    available: Availability = lambda _ctx: True

    def schema_name(self) -> str:
        return str(self.schema.get("function", {}).get("name") or self.name)


class ToolTable:
    """Budgets and dispatch for the tools offered on one answer."""

    def __init__(self, tools: list[AgentTool]) -> None:
        self._tools = tools

    @property
    def tools(self) -> list[AgentTool]:
        return list(self._tools)

    def max_turns(self) -> int:
        """Model turns: one per allowed tool call, plus one turn to answer."""
        budget = sum(max(0, tool.max_calls) for tool in self._tools)
        return min(24, budget + 1)

    def offered(self, ctx: ToolContext, *, force_answer: bool = False) -> list[AgentTool]:
        if force_answer:
            return []
        offered: list[AgentTool] = []
        for tool in self._tools:
            if ctx.calls.get(tool.name, 0) >= tool.max_calls:
                continue
            try:
                applies = tool.available(ctx)
            except Exception:
                applies = False
            if applies:
                offered.append(tool)
        return offered

    def schemas(self, offered: list[AgentTool]) -> list[dict[str, Any]] | None:
        if not offered:
            return None
        return [tool.schema for tool in offered]

    def dispatch(self, name: str, arguments: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        tool = next((item for item in self._tools if item.name == name), None)
        if tool is None:
            return {"error": f"Unknown tool: {name}"}
        used = ctx.calls.get(name, 0)
        if used >= tool.max_calls:
            return {"error": f"Tool budget exhausted for {name}; answer with what you have."}
        ctx.calls[name] = used + 1
        if ctx.write_event:
            ctx.write_event({"event": "tool_start", "name": name, "arguments": arguments})
        try:
            output = tool.run(arguments, ctx)
        finally:
            if ctx.write_event:
                ctx.write_event({"event": "tool_done", "name": name})
        if not isinstance(output, dict):
            return {"result": output}
        return output


def allowlisted(tools: list[AgentTool], mode: Mode) -> list[AgentTool]:
    """Drop tools a mode's ``tools:`` frontmatter does not list.

    An empty allowlist means every built-in tool.
    """
    allowed = getattr(mode, "tools", ()) or ()
    if not allowed:
        return tools
    names = set(allowed)
    return [tool for tool in tools if tool.name in names]
