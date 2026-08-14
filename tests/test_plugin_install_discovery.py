from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from vera_plugin_host.worker import PROTOCOL_VERSION


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SRC = ROOT / "tests" / "support" / "echo_ingest_plugin"


def _uv() -> str | None:
    found = shutil.which("uv")
    if found:
        return found
    candidate = Path.home() / ".local" / "bin" / "uv"
    return str(candidate) if candidate.is_file() else None


def _venv_python(venv: Path) -> Path:
    if sys.platform == "win32":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _create_venv(venv: Path) -> Path:
    uv = _uv()
    if uv:
        subprocess.run([uv, "venv", str(venv)], check=True)
        return _venv_python(venv)
    created = subprocess.run(
        [sys.executable, "-m", "venv", str(venv)],
        capture_output=True,
        text=True,
    )
    if created.returncode != 0:
        raise RuntimeError(
            "Unable to create a clean plugin-host venv. Install uv or a Python "
            f"with ensurepip.\n{created.stderr}"
        )
    return _venv_python(venv)


def _install(python: Path, *packages: str, editable: bool = False) -> None:
    uv = _uv()
    if uv:
        command = [uv, "pip", "install", "--python", str(python)]
        if editable:
            command.append("-e")
        command.extend(packages)
        subprocess.run(command, check=True, cwd=ROOT)
        return
    command = [str(python), "-m", "pip", "install", "-q"]
    if editable:
        command.append("-e")
    command.extend(packages)
    subprocess.run(command, check=True, cwd=ROOT)


def _uninstall(python: Path, package: str) -> None:
    uv = _uv()
    if uv:
        subprocess.run(
            [uv, "pip", "uninstall", "--python", str(python), "-y", package],
            check=True,
        )
        return
    subprocess.run([str(python), "-m", "pip", "uninstall", "-q", "-y", package], check=True)


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
    python = _create_venv(venv)
    _install(
        python,
        str(ROOT / "packages" / "vera-doc"),
        str(ROOT / "packages" / "vera-ingest"),
        str(ROOT / "packages" / "vera-ingest-pymupdf"),
    )
    _install(python, str(PLUGIN_SRC))
    wheel_result = _plugin_host_ping(python)
    assert wheel_result["protocol"] == PROTOCOL_VERSION
    assert "echo" in wheel_result["pipelines"]
    assert "pymupdf" in wheel_result["pipelines"]

    _uninstall(python, "echo-ingest-plugin")
    missing = _plugin_host_ping(python)
    assert "echo" not in missing["pipelines"]

    _install(python, str(PLUGIN_SRC), editable=True)
    editable_result = _plugin_host_ping(python)
    assert "echo" in editable_result["pipelines"]
