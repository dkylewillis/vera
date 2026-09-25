"""Sidecar mcp-bridge entry: fail closed and never auto-install deps."""

from __future__ import annotations

import os

from vera_app import sidecar as module
from vera_mcp.access_policy import POLICY_ENV


def test_sidecar_mcp_bridge_fail_closed_without_policy(monkeypatch, capsys):
    monkeypatch.delenv(POLICY_ENV, raising=False)
    assert module._run_mcp_bridge() == 2
    err = capsys.readouterr().err
    assert POLICY_ENV in err


def test_sidecar_mcp_bridge_strips_semantic_auto_install(monkeypatch):
    monkeypatch.setenv("VERA_AUTO_INSTALL_SEMANTIC_DEPS", "1")
    seen: list[str | None] = []

    def fake_main_bridge() -> int:
        seen.append(os.environ.get("VERA_AUTO_INSTALL_SEMANTIC_DEPS"))
        return 0

    monkeypatch.setattr("vera_mcp.server.main_bridge", fake_main_bridge)
    assert module._run_mcp_bridge() == 0
    assert seen == [None]


def test_sidecar_mcp_bridge_requires_vera_mcp(monkeypatch, capsys):
    import builtins

    real_import = builtins.__import__

    def blocker(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "vera_mcp.server":
            raise ImportError("simulated missing vera-mcp")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", blocker)
    assert module._run_mcp_bridge() == 2
    err = capsys.readouterr().err
    assert "vera-mcp" in err
    assert "simulated missing vera-mcp" in err
