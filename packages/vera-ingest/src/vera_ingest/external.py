"""Pipelines that run in a separate Python environment.

``VERA_PIPELINE_PYTHON`` names a Python interpreter, or the folder of a
virtual environment, that has ``vera-ingest`` and pipelines this process does
not ship (Docling, for example). Pipeline discovery asks that interpreter
which pipelines it has, and :func:`vera_ingest.convert` runs the whole
conversion there when the chosen pipeline is one of them. This process reads
the finished ``.vera`` archive as usual, so search needs nothing from that
environment.

The child never inherits ``VERA_PIPELINE_PYTHON``, so it cannot hand the work
on to a third interpreter.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from collections import deque
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .cancellation import raise_if_cancelled
from .descriptors import PipelineDescriptor

EXTERNAL_PYTHON_ENV = "VERA_PIPELINE_PYTHON"

__all__ = [
    "EXTERNAL_PYTHON_ENV",
    "ExternalPipelineError",
    "configured_python",
    "list_external_descriptors",
    "resolve_python",
    "run_external_convert",
]

_MARKER = "VERA_EXTERNAL_RESULT:"
_LIST_TIMEOUT_SECONDS = 120
_POLL_SECONDS = 0.1
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_PYTHON_CANDIDATES = (
    ("Scripts", "python.exe"),
    ("bin", "python"),
    ("bin", "python3"),
    ("python.exe",),
)

# Both scripts use single quotes only, so they survive Windows argument quoting.
_LIST_SCRIPT = f"""
import json
from vera_ingest import list_ingest_pipeline_descriptors
try:
    found = list_ingest_pipeline_descriptors(include_variants=True)
except TypeError:
    found = list_ingest_pipeline_descriptors()
print()
print('{_MARKER}' + json.dumps({{'pipelines': [item.as_dict() for item in found]}}))
"""

_CONVERT_SCRIPT = f"""
import json
import sys
request = json.loads(sys.stdin.read())
try:
    from vera_ingest import convert
    reply = {{'ok': True, 'output': convert(request['input'], request['output'], **request['options'])}}
except Exception as exc:
    reply = {{'ok': False, 'error': str(exc) or type(exc).__name__}}
print()
print('{_MARKER}' + json.dumps(reply))
sys.exit(0 if reply['ok'] else 1)
"""


class ExternalPipelineError(ValueError):
    """The separate Python environment is missing, broken, or failed a conversion."""


def resolve_python(location: str | Path) -> Path:
    """Return the interpreter for ``location``: a Python executable or an environment folder."""
    path = Path(location).expanduser()
    if path.is_dir():
        for parts in _PYTHON_CANDIDATES:
            candidate = path.joinpath(*parts)
            if candidate.is_file():
                return candidate
        raise ExternalPipelineError(
            f"No Python interpreter found in {path}. Choose a virtual environment "
            "folder such as .venv, or the python executable inside it."
        )
    if path.is_file():
        return path
    raise ExternalPipelineError(f"{path} does not exist.")


def configured_python() -> str:
    """The raw ``VERA_PIPELINE_PYTHON`` value, or ``""`` when no environment is set."""
    return os.environ.get(EXTERNAL_PYTHON_ENV, "").strip()


def _child_env(temp_dir: str | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env.pop(EXTERNAL_PYTHON_ENV, None)
    env.pop("PYTHONHOME", None)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    if temp_dir:
        # A stopped conversion leaves its half-written archive here, not in the
        # shared temp folder, so the caller can delete it.
        for name in ("TMP", "TEMP", "TMPDIR"):
            env[name] = temp_dir
    return env


def _marked_reply(stdout: str) -> dict[str, Any] | None:
    for line in reversed(stdout.splitlines()):
        if line.startswith(_MARKER):
            try:
                reply = json.loads(line[len(_MARKER) :])
            except ValueError:
                return None
            return reply if isinstance(reply, dict) else None
    return None


def _failure_detail(python: Path, stderr_lines: list[str]) -> str:
    text = "\n".join(stderr_lines)
    if "No module named 'vera_ingest'" in text:
        return (
            f"{python} does not have VERA installed. Install it in that environment, "
            'for example: pip install "vera[docling]"'
        )
    for line in reversed(stderr_lines):
        if line.strip() and " timing step=" not in line:
            return line.strip()
    return ""


def list_external_descriptors(python: str | Path) -> list[PipelineDescriptor]:
    """Ask the interpreter at ``python`` for its installed pipeline descriptors."""
    interpreter = resolve_python(python)
    try:
        completed = subprocess.run(
            [str(interpreter), "-c", _LIST_SCRIPT],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            timeout=_LIST_TIMEOUT_SECONDS,
            env=_child_env(),
            creationflags=_NO_WINDOW,
        )
    except subprocess.TimeoutExpired as exc:
        raise ExternalPipelineError(
            f"{interpreter} did not list its pipelines within {_LIST_TIMEOUT_SECONDS} seconds."
        ) from exc
    except OSError as exc:
        raise ExternalPipelineError(f"Could not start {interpreter}: {exc}") from exc
    reply = _marked_reply(completed.stdout)
    if completed.returncode != 0 or reply is None:
        detail = _failure_detail(interpreter, completed.stderr.splitlines())
        raise ExternalPipelineError(
            detail
            or f"{interpreter} could not list its pipelines (exit code {completed.returncode})."
        )
    descriptors = []
    for raw in reply.get("pipelines") or ():
        try:
            descriptors.append(PipelineDescriptor.from_dict(raw))
        except (TypeError, ValueError):
            continue
    return descriptors


def _forward_stderr(stream: Any, tail: deque[str]) -> None:
    """Pass the child's timing and progress lines through to this process's stderr."""
    for line in stream:
        tail.append(line.rstrip())
        try:
            sys.stderr.write(line)
            sys.stderr.flush()
        except Exception:  # noqa: BLE001 - a closed or missing stderr must not stop the conversion
            pass


def _stop(process: subprocess.Popen[str]) -> None:
    """Stop the child and anything it started (a venv launcher starts the real interpreter)."""
    if process.poll() is None:
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    timeout=15,
                    creationflags=_NO_WINDOW,
                )
            else:
                os.killpg(process.pid, signal.SIGKILL)
        except (OSError, subprocess.SubprocessError):
            pass
    if process.poll() is None:
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        pass


def run_external_convert(
    python: str | Path,
    input_path: str,
    output_path: str,
    options: Mapping[str, Any],
    *,
    cancel: Any | None = None,
) -> str:
    """Run ``vera_ingest.convert`` in the interpreter at ``python`` and return the output path.

    ``options`` are ``convert`` keyword arguments and must be JSON values.
    ``cancel`` is polled while the child runs; a cancel or skip stops the
    child and re-raises.
    """
    interpreter = resolve_python(python)
    try:
        payload = json.dumps(
            {
                "input": str(input_path),
                "output": str(output_path),
                "options": {key: value for key, value in options.items() if value is not None},
            }
        )
    except (TypeError, ValueError) as exc:
        raise ExternalPipelineError(
            "Options for a pipeline in a separate Python environment must be plain "
            f"JSON values: {exc}"
        ) from exc
    temp_dir = tempfile.mkdtemp(prefix="vera-external-")
    try:
        try:
            process = subprocess.Popen(
                [str(interpreter), "-c", _CONVERT_SCRIPT],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=_child_env(temp_dir),
                creationflags=_NO_WINDOW,
                start_new_session=os.name != "nt",
            )
        except OSError as exc:
            raise ExternalPipelineError(f"Could not start {interpreter}: {exc}") from exc
        assert process.stdin is not None and process.stdout is not None
        stdout_lines: list[str] = []
        stderr_tail: deque[str] = deque(maxlen=40)
        readers = [
            threading.Thread(target=stdout_lines.extend, args=(process.stdout,), daemon=True),
            threading.Thread(
                target=_forward_stderr, args=(process.stderr, stderr_tail), daemon=True
            ),
        ]
        for reader in readers:
            reader.start()
        try:
            try:
                process.stdin.write(payload)
                process.stdin.close()
            except OSError:
                pass  # the child already exited; its exit code and stderr say why
            while True:
                raise_if_cancelled(cancel)
                try:
                    process.wait(timeout=_POLL_SECONDS)
                    break
                except subprocess.TimeoutExpired:
                    continue
        except BaseException:
            _stop(process)
            raise
        finally:
            for reader in readers:
                reader.join(timeout=5)
        reply = _marked_reply("".join(stdout_lines))
        if reply is not None and reply.get("ok") and process.returncode == 0:
            return str(reply.get("output") or output_path)
        if reply is not None and reply.get("error"):
            raise ExternalPipelineError(str(reply["error"]))
        detail = _failure_detail(interpreter, list(stderr_tail))
        raise ExternalPipelineError(
            detail
            or f"{interpreter} stopped before the conversion finished "
            f"(exit code {process.returncode})."
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
