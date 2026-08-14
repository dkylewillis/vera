from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = ROOT / "packages" / "vera-app" / "scripts" / "build-sidecar.cjs"

# Packages the frozen sidecar needs for semantic (Sentence Transformers)
# embeddings. Excluding any of them silently downgrades a built installer to
# hashing-only embeddings.
SEMANTIC_REQUIREMENTS = {
    "torch",
    "torchgen",
    "transformers",
    "sentence_transformers",
    "tokenizers",
    "safetensors",
    "huggingface_hub",
    "numpy",
}

_BLOCKED_IMPORT_PROBE = """
import sys
import importlib.abc

blocked = sys.argv[1]


class _Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == blocked or fullname.startswith(blocked + "."):
            raise ModuleNotFoundError(f"No module named {fullname!r}", name=fullname)
        return None


sys.meta_path.insert(0, _Blocker())

import torch  # noqa: F401
"""


def _excluded_modules() -> list[str]:
    source = BUILD_SCRIPT.read_text(encoding="utf-8")
    match = re.search(r"const excludedModules = \[(.*?)\];", source, re.DOTALL)
    assert match, "build-sidecar.cjs no longer declares an excludedModules array"
    return re.findall(r'"([^"]+)"', match.group(1))


def _is_installed(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def test_excluded_modules_reach_pyinstaller() -> None:
    modules = _excluded_modules()
    assert modules
    assert '"--exclude-module"' in BUILD_SCRIPT.read_text(encoding="utf-8")


def test_packaged_app_ships_plugin_host_source() -> None:
    package_json = (ROOT / "packages" / "vera-app" / "package.json").read_text(encoding="utf-8")
    assert "python/plugin-host/vera_plugin_host" in package_json
    assert (ROOT / "packages" / "vera-app" / "src" / "vera_plugin_host" / "__main__.py").is_file()
    excluded = set(_excluded_modules())
    assert excluded.isdisjoint(SEMANTIC_REQUIREMENTS), (
        "build-sidecar.cjs excludes modules the semantic embedder needs: "
        f"{sorted(excluded & SEMANTIC_REQUIREMENTS)}"
    )


@pytest.mark.parametrize("module", sorted(_excluded_modules()))
def test_excluded_module_is_not_needed_to_import_torch(module: str) -> None:
    """Every exclusion must be droppable without breaking ``import torch``.

    ``torchgen`` reads like build-time codegen but is imported unconditionally by
    ``torch.utils._python_dispatch``, so excluding it produced a sidecar that
    raised ``ModuleNotFoundError`` as soon as a neural model was selected.
    """
    pytest.importorskip("torch")
    if not _is_installed(module):
        pytest.skip(f"{module} is not installed; excluding it is a no-op here")
    probe = subprocess.run(
        [sys.executable, "-c", _BLOCKED_IMPORT_PROBE, module],
        capture_output=True,
        text=True,
    )
    assert probe.returncode == 0, (
        f"excluding {module!r} breaks `import torch` in the frozen sidecar:\n"
        f"{probe.stderr.strip()}"
    )
