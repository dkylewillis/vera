"""Plugin sidecar handlers. Electron main sets ``plugins_dir``; the renderer cannot."""

from __future__ import annotations

from typing import Any

from vera_app.types import Request
from vera_ingest import external_pipeline_status, list_ingest_pipeline_load_errors
from vera_ingest.plugins import install_plugin_wheel, list_plugins, remove_plugin


def _plugins_dir(request: Request) -> str:
    value = request.get("plugins_dir")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("plugins_dir is required")
    return value


def handle_plugins_list(request: Request) -> dict[str, Any]:
    """Installed plugins, the separate Python environment, and pipelines that failed to load.

    ``environment`` is ``{"python", "pipelines"}``: the location Electron main
    passed in ``VERA_PIPELINE_PYTHON`` (empty when none is set) and the
    pipelines that run there.
    """
    return {
        "plugins_dir": _plugins_dir(request),
        "plugins": list_plugins(_plugins_dir(request)),
        "environment": external_pipeline_status(),
        "load_errors": list_ingest_pipeline_load_errors(),
    }


def handle_plugin_install(request: Request) -> dict[str, Any]:
    """Unpack a pure-Python plugin wheel; the app restarts the sidecar to load it."""
    wheel = request.get("wheel")
    if not isinstance(wheel, str) or not wheel.strip():
        raise ValueError("wheel is required")
    return install_plugin_wheel(wheel, _plugins_dir(request))


def handle_plugin_remove(request: Request) -> dict[str, Any]:
    name = request.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name is required")
    return remove_plugin(name, _plugins_dir(request))
