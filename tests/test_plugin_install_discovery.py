from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from vera_plugin_host.worker import PROTOCOL_VERSION


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SRC = ROOT / "tests" / "support" / "echo_ingest_plugin"


def _venv_python(venv: Path) -> Path:
    if sys.platform == "win32":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _install(python: Path, *packages: str, editable: bool = False) -> None:
    command = [str(python), "-m", "pip", "install", "-q"]
    if editable:
        command.append("-e")
    command.extend(packages)
    subprocess.run(command, check=True, cwd=ROOT)


def _plugin_host_ping(python: Path) -> dict:
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "packages" / "vera-app" / "src"),
        "PYTHONUNBUFFERED": "1",
        "PYTHONNOUSERSITE": "1",
    }
    proc = subprocess.Popen(
        [str(python), "-m", "vera_plugin_host"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    try:
        assert proc.stdin is not None
        assert proc.stdout is not None
        proc.stdin.write('{"id":"1","action":"ping"}\n')
        proc.stdin.flush()
        line = proc.stdout.readline()
        assert line, proc.stderr.read()
        payload = json.loads(line)
        assert payload["ok"] is True, payload
        return payload["result"]
    finally:
        if proc.stdin:
            proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=10)


def test_plugin_host_discovers_pip_and_editable_plugin_installs(tmp_path):
    venv = tmp_path / "plugin-env"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    python = _venv_python(venv)
    _install(
        python,
        str(ROOT / "packages" / "vera-doc"),
        str(ROOT / "packages" / "vera-ingest"),
    )
    _install(python, str(PLUGIN_SRC))
    wheel_result = _plugin_host_ping(python)
    assert wheel_result["protocol"] == PROTOCOL_VERSION
    assert "echo" in wheel_result["pipelines"]
    assert "pymupdf" in wheel_result["pipelines"]

    subprocess.run([str(python), "-m", "pip", "uninstall", "-q", "-y", "echo-ingest-plugin"], check=True)
    missing = _plugin_host_ping(python)
    assert "echo" not in missing["pipelines"]

    _install(python, str(PLUGIN_SRC), editable=True)
    editable_result = _plugin_host_ping(python)
    assert "echo" in editable_result["pipelines"]
