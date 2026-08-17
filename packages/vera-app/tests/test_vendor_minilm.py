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


def test_snapshot_is_complete_requires_weights(tmp_path: Path):
    vendor = _load_vendor()
    dest = tmp_path / "all-MiniLM-L6-v2"
    dest.mkdir()
    assert vendor.snapshot_is_complete(dest) is False
    for name in vendor.REQUIRED_FILES:
        path = dest / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("stub", encoding="utf-8")
    assert vendor.snapshot_is_complete(dest) is True
    vendor.verify_snapshot(dest)


def test_verify_snapshot_lists_missing_files(tmp_path: Path):
    vendor = _load_vendor()
    dest = tmp_path / "empty"
    dest.mkdir()
    with pytest.raises(SystemExit, match="missing"):
        vendor.verify_snapshot(dest)


def test_vendor_reuses_complete_snapshot_without_download(tmp_path: Path):
    vendor = _load_vendor()
    dest = tmp_path / "all-MiniLM-L6-v2"
    dest.mkdir()
    for name in vendor.REQUIRED_FILES:
        path = dest / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("stub", encoding="utf-8")
    vendor.vendor_minilm(dest)
    assert (dest / "vera-minilm-manifest.json").is_file()
