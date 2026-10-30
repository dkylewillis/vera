"""Loopback MCP service shared by local agents.

Desktop (or a future ``vera serve``) starts one process:

    VERA_SERVICE_TOKEN=... python -m vera_mcp.service --policy policy.json --port 47821

The token is read from the environment, never from argv. The process binds
``127.0.0.1`` only, requires a bearer token on ``/mcp``, and refuses browser
``Origin`` headers. ``GET /healthz`` stays unauthenticated so a supervisor can
probe it. ``vera mcp`` (stdio, unrestricted) is unchanged.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hmac
import json
import os
import socket
import sys
import threading
import time
from collections.abc import Callable, Iterator
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import anyio

from .access_policy import AccessPolicy

TOKEN_ENV = "VERA_SERVICE_TOKEN"
DEFAULT_PORT = 47821
_AUTO_INSTALL_SEMANTIC_DEPS = "VERA_AUTO_INSTALL_SEMANTIC_DEPS"
_WARM_MODEL = "sentence-transformers:all-MiniLM-L6-v2"


def service_version() -> str:
    try:
        return version("vera-mcp")
    except PackageNotFoundError:
        return "0"


def warm_default_embedder() -> None:
    """Load the Desktop default embedder so the first semantic search is warm.

    A missing optional model is logged and ignored. Keyword search and hashing
    archives still work.
    """
    try:
        from vera_doc.embeddings import get_embedder

        get_embedder(_WARM_MODEL).embed(["vera"])
    except Exception as exc:
        print(f"vera-service: embedder warm-up skipped ({exc})", file=sys.stderr, flush=True)


class LoopbackGuardMiddleware:
    """Bearer token, exact loopback Host, and no browser Origin."""

    def __init__(self, app: Any, *, token: str, port: int) -> None:
        self.app = app
        self._token = token.encode("utf-8")
        self._hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = _header_map(scope)
        if headers.get("host", "") not in self._hosts:
            await _reject(send, 421, "Invalid Host header")
            return
        if "origin" in headers:
            await _reject(send, 403, "Origin header is not allowed")
            return
        if scope.get("path") != "/healthz" and not _bearer_ok(headers.get("authorization", ""), self._token):
            await _reject(send, 401, "Unauthorized")
            return
        await self.app(scope, receive, send)


def serve(
    policy: AccessPolicy,
    *,
    host: str = "127.0.0.1",
    port: int,
    token: str,
    state_file: str | Path | None = None,
    on_started: Callable[[Any], None] | None = None,
) -> int:
    """Serve MCP until the process is stopped. Returns 0, or 1 if the port is taken."""
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("VERA agent service only binds to loopback.")
    if not isinstance(port, int) or port < 1 or port > 65535:
        raise ValueError("VERA agent service requires a TCP port between 1 and 65535.")
    if not token or not str(token).strip():
        raise ValueError("VERA agent service requires a token.")
    os.environ.pop(_AUTO_INSTALL_SEMANTIC_DEPS, None)

    bound = _bind_loopback(port)
    if bound is None:
        print(
            f"VERA agent service could not bind 127.0.0.1:{port}. Choose another port.",
            file=sys.stderr,
            flush=True,
        )
        return 1

    import uvicorn

    app = build_service_app(policy, token=token.strip(), port=port)
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    server.install_signal_handlers = threading.current_thread() is threading.main_thread()
    state_path = Path(state_file) if state_file else None
    wrote = False

    async def _run() -> None:
        nonlocal wrote
        task = asyncio.create_task(server.serve(sockets=[bound]))
        for _ in range(200):
            if server.started or task.done():
                break
            await asyncio.sleep(0.05)
        if not server.started:
            server.should_exit = True
            with contextlib.suppress(Exception):
                await task
            raise RuntimeError(
                f"VERA agent service failed while starting on 127.0.0.1:{port}."
            )
        if state_path is not None:
            _write_state(state_path, port)
            wrote = True
        if on_started is not None:
            on_started(server)
        await task

    try:
        asyncio.run(_run())
    finally:
        if not server.started:
            bound.close()
        if wrote and state_path is not None:
            _remove_state(state_path)
    return 0


def build_service_app(policy: AccessPolicy, *, token: str, port: int) -> Any:
    """Starlette app: Streamable HTTP at ``/mcp`` plus unauthenticated ``/healthz``."""
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    from .server import build_server

    mcp = build_server(policy=policy)
    _offload_sync_tools(mcp)
    reported = service_version()

    @mcp.custom_route("/healthz", methods=["GET"], include_in_schema=False)
    async def healthz(_request: Request) -> JSONResponse:
        return JSONResponse({"ok": True, "version": reported})

    app = mcp.streamable_http_app()
    app.add_middleware(LoopbackGuardMiddleware, token=token, port=port)
    return app


def main_service(argv: list[str] | None = None) -> int:
    """CLI entry for ``mcp-service``. Exit 2 when the policy or token is missing."""
    os.environ.pop(_AUTO_INSTALL_SEMANTIC_DEPS, None)
    parser = argparse.ArgumentParser(prog="vera-mcp-service")
    parser.add_argument("--policy", default="")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--state-file", default="")
    parser.add_argument("--warm", action="store_true")
    args = parser.parse_args(argv)
    token = (os.environ.get(TOKEN_ENV) or "").strip()
    policy_path = str(args.policy or "").strip()
    if not policy_path or not token:
        print(
            f"VERA agent service requires --policy and {TOKEN_ENV}.",
            file=sys.stderr,
            flush=True,
        )
        return 2
    try:
        policy = AccessPolicy.load(policy_path)
    except ValueError as exc:
        print(str(exc), file=sys.stderr, flush=True)
        return 2
    if args.warm:
        warm_default_embedder()
    try:
        return serve(
            policy,
            port=args.port,
            token=token,
            state_file=args.state_file or None,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr, flush=True)
        return 2


@contextlib.contextmanager
def running_service(
    policy: AccessPolicy,
    *,
    port: int,
    token: str,
    state_file: str | Path | None = None,
) -> Iterator[Any]:
    """Start ``serve`` on a daemon thread and stop it when the block exits."""
    started = threading.Event()
    holder: dict[str, Any] = {}
    errors: list[BaseException] = []

    def _on_started(server: Any) -> None:
        holder["server"] = server
        started.set()

    def _target() -> None:
        try:
            code = serve(
                policy,
                port=port,
                token=token,
                state_file=state_file,
                on_started=_on_started,
            )
            holder["code"] = code
        except BaseException as exc:  # pragma: no cover - surfaced via errors
            errors.append(exc)
        finally:
            started.set()

    thread = threading.Thread(target=_target, name="vera-service", daemon=True)
    thread.start()
    if not started.wait(timeout=15):
        raise RuntimeError("VERA agent service did not start.")
    if errors:
        raise errors[0]
    if "server" not in holder:
        raise RuntimeError(
            f"VERA agent service exited before listening (code {holder.get('code', 1)})."
        )
    try:
        yield holder["server"]
    finally:
        holder["server"].should_exit = True
        thread.join(timeout=10)


def _offload_sync_tools(mcp: Any) -> None:
    """Run synchronous tools off the event loop and log the call, not the query."""
    for tool in mcp._tool_manager.list_tools():
        if tool.is_async:
            continue
        original = tool.fn
        tool_name = tool.name

        async def wrapped(*args: Any, __fn: Any = original, __name: str = tool_name, **kwargs: Any) -> Any:
            started = time.perf_counter()
            try:
                return await anyio.to_thread.run_sync(
                    lambda fn=__fn, args=args, kwargs=kwargs: fn(*args, **kwargs)
                )
            finally:
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                print(
                    f"vera-service tool={__name} archive={_archive_label(kwargs)} ms={elapsed_ms}",
                    file=sys.stderr,
                    flush=True,
                )

        tool.fn = wrapped
        tool.is_async = True


def _archive_label(arguments: dict[str, Any]) -> str:
    raw = arguments.get("file") or arguments.get("directory") or ""
    if not isinstance(raw, str) or not raw.strip():
        return "-"
    return Path(raw).name


def _bind_loopback(port: int) -> socket.socket | None:
    """Bind exclusively so a taken port fails before uvicorn calls ``sys.exit``."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
        sock.listen(2048)
        sock.setblocking(False)
    except OSError:
        sock.close()
        return None
    return sock


def _write_state(path: Path, port: int) -> None:
    payload = {
        "url": f"http://127.0.0.1:{port}/mcp",
        "pid": os.getpid(),
        "version": service_version(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _remove_state(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return


def _header_map(scope: dict[str, Any]) -> dict[str, str]:
    found: dict[str, str] = {}
    for key, value in scope.get("headers") or []:
        name = key.decode("latin1").lower()
        if name not in found:
            found[name] = value.decode("latin1")
    return found


def _bearer_ok(authorization: str, expected: bytes) -> bool:
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        return False
    presented = authorization[len(prefix) :].strip().encode("utf-8")
    if not presented:
        return False
    return hmac.compare_digest(presented, expected)


async def _reject(send: Any, status: int, message: str) -> None:
    body = message.encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"text/plain; charset=utf-8"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


if __name__ == "__main__":
    raise SystemExit(main_service())
