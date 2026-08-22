"""Offline checks for the MiniLM vendor helper."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "vendor_minilm.py"


def _load_vendor():
    spec = importlib.util.spec_from_file_location("vendor_minilm", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repo_snapshot_matches_pinned_hash():
    vendor = _load_vendor()
    snapshot = Path(__file__).resolve().parents[1] / "build" / "minilm" / "all-MiniLM-L6-v2"
    if not vendor.snapshot_is_complete(snapshot):
        pytest.skip("vendored MiniLM ONNX snapshot is not present")
    vendor.verify_snapshot(snapshot)
    for name in vendor.FORBIDDEN_FILES:
        assert not (snapshot / name).is_file()


def test_snapshot_is_complete_requires_weights(tmp_path: Path):
    vendor = _load_vendor()
    dest = tmp_path / "all-MiniLM-L6-v2"
    dest.mkdir()
    assert vendor.snapshot_is_complete(dest) is False
    for name in vendor.REQUIRED_FILES:
        path = dest / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"stub")
    assert vendor.snapshot_is_complete(dest) is True
    vendor.verify_snapshot(dest, check_hash=False)


def test_verify_snapshot_lists_missing_files(tmp_path: Path):
    vendor = _load_vendor()
    dest = tmp_path / "empty"
    dest.mkdir()
    with pytest.raises(SystemExit, match="missing"):
        vendor.verify_snapshot(dest)


def test_vendor_reuses_complete_snapshot_without_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    vendor = _load_vendor()
    dest = tmp_path / "all-MiniLM-L6-v2"
    dest.mkdir()
    for name in vendor.REQUIRED_FILES:
        (dest / name).write_bytes(b"stub")
    monkeypatch.setattr(vendor, "EXPECTED_MODEL_SHA256", vendor.sha256_file(dest / "model.onnx"))
    vendor.vendor_minilm(dest)
    assert (dest / "vera-minilm-manifest.json").is_file()
    payload = (dest / "vera-minilm-manifest.json").read_text(encoding="utf-8")
    assert "model_onnx_sha256" in payload


def test_vendor_strips_pytorch_weights(tmp_path: Path):
    vendor = _load_vendor()
    dest = tmp_path / "all-MiniLM-L6-v2"
    dest.mkdir()
    for name in vendor.REQUIRED_FILES:
        (dest / name).write_bytes(b"stub")
    (dest / "model.safetensors").write_bytes(b"nope")
    (dest / ".export-src").mkdir()
    (dest / ".export-src" / "model.safetensors").write_bytes(b"nope")
    vendor.strip_non_onnx_artifacts(dest)
    assert not (dest / "model.safetensors").exists()
    assert not (dest / ".export-src").exists()


def test_verify_snapshot_rejects_hash_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    vendor = _load_vendor()
    dest = tmp_path / "all-MiniLM-L6-v2"
    dest.mkdir()
    for name in vendor.REQUIRED_FILES:
        (dest / name).write_bytes(b"stub")
    monkeypatch.setattr(vendor, "EXPECTED_MODEL_SHA256", "0" * 64)
    with pytest.raises(SystemExit, match="sha256"):
        vendor.verify_snapshot(dest)
