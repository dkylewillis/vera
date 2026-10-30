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


def test_sidecar_mcp_service_requires_token_and_policy(monkeypatch, capsys, tmp_path):
    import sys

    monkeypatch.delenv("VERA_SERVICE_TOKEN", raising=False)
    monkeypatch.setenv("VERA_AUTO_INSTALL_SEMANTIC_DEPS", "1")
    monkeypatch.setattr(sys, "argv", ["vera-sidecar", "mcp-service"])
    assert module._dispatch_early_command(["vera-sidecar", "mcp-service"]) == 2
    err = capsys.readouterr().err
    assert "VERA_SERVICE_TOKEN" in err
    assert "VERA_AUTO_INSTALL_SEMANTIC_DEPS" not in os.environ

    monkeypatch.setenv("VERA_SERVICE_TOKEN", "token")
    missing = tmp_path / "missing.json"
    monkeypatch.setattr(sys, "argv", ["vera-sidecar", "mcp-service", "--policy", str(missing)])
    assert module._run_mcp_service() == 2
    assert "missing" in capsys.readouterr().err


def test_sidecar_mcp_connect_requires_connect_file(monkeypatch, capsys):
    import sys

    monkeypatch.setattr(sys, "argv", ["vera-sidecar", "mcp-connect"])
    assert module._dispatch_early_command(["vera-sidecar", "mcp-connect"]) == 2
    assert "Agent access" in capsys.readouterr().err


def test_sidecar_json_mode_is_not_an_mcp_command():
    assert module._dispatch_early_command(["vera-sidecar"]) is None
    assert module._dispatch_early_command(["vera-sidecar", "not-mcp"]) is None


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
