"""JSON-lines client for the shipped ``vera_plugin_host`` worker."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from vera_app.cancellation import CancellationToken, CancelledError
from vera_app.runtime import plugin_host_spawn_env

EventCallback = Callable[[dict[str, Any]], None]
_request_cancel: ContextVar[CancellationToken | None] = ContextVar(
    "vera_plugin_host_cancel",
    default=None,
)


@contextmanager
def bind_request_cancel(cancel: CancellationToken | None) -> Iterator[None]:
    """Expose the current sidecar cancel token to in-flight host embeds."""
    token = _request_cancel.set(cancel)
    try:
        yield
    finally:
        _request_cancel.reset(token)


def current_request_cancel() -> CancellationToken | None:
    return _request_cancel.get()


class PluginHostError(RuntimeError):
    """Raised when the plugin host fails or returns an error payload."""


class PluginHost:
    """Spawn and talk to ``python -m vera_plugin_host`` over stdin/stdout."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc: subprocess.Popen[str] | None = None
        self._pending: dict[str, dict[str, Any]] = {}
        self._reader: threading.Thread | None = None
        self._stdout_buffer = ""
        self._command: dict[str, Any] | None = None

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def configure(
        self,
        *,
        executable: str,
        plugin_host_root: str,
        artifacts_path: str = "",
        extra_env: dict[str, str] | None = None,
    ) -> None:
        command = {
            "executable": executable,
            "plugin_host_root": plugin_host_root,
            "artifacts_path": artifacts_path,
            "extra_env": dict(extra_env or {}),
        }
        with self._lock:
            changed = command != self._command
            self._command = command
        if changed and self.running:
            self.restart()

    def stop(self) -> None:
        self._kill("Plugin host stopped")

    def restart(self) -> None:
        self._kill("Plugin host restarted")

    def request(
        self,
        payload: dict[str, Any],
        *,
        timeout: float | None = None,
        cancel: CancellationToken | None = None,
        on_event: EventCallback | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        proc = self._ensure_started()
        request_id = request_id or uuid.uuid4().hex
        message = {**payload, "id": request_id}
        done = threading.Event()
        slot: dict[str, Any] = {
            "event": done,
            "on_event": on_event,
            "response": None,
            "error": None,
        }
        with self._lock:
            self._pending[request_id] = slot
        try:
            if proc.stdin is None or proc.stdin.closed:
                raise PluginHostError("Plugin host stdin is not writable")
            proc.stdin.write(json.dumps(message) + "\n")
            proc.stdin.flush()
        except Exception as exc:
            with self._lock:
                self._pending.pop(request_id, None)
            raise PluginHostError(str(exc) or "Unable to write to the plugin host") from exc

        deadline = None if timeout is None else timeout
        while True:
            if cancel and cancel.cancelled:
                self._send_control("cancel", request_id)
                raise CancelledError(
                    "Embedding cancelled"
                    if payload.get("action") in {"embed", "embedder_info"}
                    else "Request cancelled"
                )
            if (
                cancel
                and cancel.skip_requested
                and payload.get("action") in {"convert", "batch_convert"}
            ):
                self._send_control("skip", request_id)
            if done.wait(timeout=0.05):
                break
            if deadline is not None:
                deadline -= 0.05
                if deadline <= 0:
                    self._send_control("cancel", request_id)
                    with self._lock:
                        self._pending.pop(request_id, None)
                    raise PluginHostError(
                        f"Plugin host {payload.get('action', 'request')} timed out after {timeout:.0f}s"
                    )
        if slot["error"] is not None:
            raise PluginHostError(str(slot["error"]))
        response = slot["response"]
        if not isinstance(response, dict):
            raise PluginHostError("Plugin host returned an empty response")
        if response.get("cancelled"):
            raise CancelledError(str(response.get("error") or "Request cancelled"))
        if not response.get("ok"):
            raise PluginHostError(str(response.get("error") or "Plugin host request failed"))
        result = response.get("result")
        return result if isinstance(result, dict) else {}

    def _send_control(self, action: str, target_id: str) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None or proc.stdin.closed:
            return
        try:
            proc.stdin.write(
                json.dumps({"id": uuid.uuid4().hex, "action": action, "target_id": target_id})
                + "\n"
            )
            proc.stdin.flush()
        except Exception:
            return

    def _ensure_started(self) -> subprocess.Popen[str]:
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return self._proc
            command = self._command
            if not command:
                raise PluginHostError("Plugin host is not configured.")
            env = os.environ.copy()
            env.update(
                plugin_host_spawn_env(
                    plugin_host_root=str(command["plugin_host_root"]),
                    artifacts_path=str(command.get("artifacts_path") or ""),
                    extra_env=command.get("extra_env") or {},
                )
            )
            kwargs: dict[str, Any] = {
                "args": [str(command["executable"]), "-m", "vera_plugin_host"],
                "stdin": subprocess.PIPE,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "text": True,
                "bufsize": 1,
                "env": env,
            }
            if sys.platform == "win32":
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self._proc = subprocess.Popen(**kwargs)
            self._stdout_buffer = ""
            self._reader = threading.Thread(target=self._read_stdout, daemon=True)
            self._reader.start()
            threading.Thread(target=self._drain_stderr, daemon=True).start()
            return self._proc

    def _kill(self, reason: str) -> None:
        with self._lock:
            proc = self._proc
            self._proc = None
            pending = list(self._pending.items())
            self._pending.clear()
        for _request_id, slot in pending:
            slot["error"] = PluginHostError(reason)
            slot["event"].set()
        if proc is not None:
            proc.kill()

    def _read_stdout(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        try:
            for line in proc.stdout:
                self._handle_line(line)
        except Exception as exc:
            self._fail_pending(exc)
        finally:
            if self._proc is proc:
                self._fail_pending(PluginHostError("Plugin host exited"))
                self._proc = None

    def _drain_stderr(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        for line in proc.stderr:
            text = line.rstrip()
            if text:
                print(f"[vera-plugin-host] {text}", file=sys.stderr)

    def _handle_line(self, line: str) -> None:
        text = line.strip()
        if not text:
            return
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            print(f"[vera-plugin-host] Ignoring invalid stdout line: {text}", file=sys.stderr)
            return
        if not isinstance(payload, dict) or not payload.get("id"):
            return
        request_id = str(payload["id"])
        with self._lock:
            slot = self._pending.get(request_id)
        if slot is None:
            return
        if "event" in payload and "ok" not in payload:
            callback = slot.get("on_event")
            if callback:
                callback(payload)
            return
        slot["response"] = payload
        with self._lock:
            self._pending.pop(request_id, None)
        slot["event"].set()

    def _fail_pending(self, error: Exception) -> None:
        with self._lock:
            pending = list(self._pending.items())
            self._pending.clear()
        for _request_id, slot in pending:
            slot["error"] = error
            slot["event"].set()
