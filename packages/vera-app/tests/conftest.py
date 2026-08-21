import pytest


@pytest.fixture(autouse=True)
def skip_sidecar_torch_warmup(monkeypatch):
    """Sidecar tests must not import Torch (slow, and can deadlock on Windows)."""
    monkeypatch.setenv("VERA_SIDECAR_SKIP_TORCH_WARMUP", "1")
