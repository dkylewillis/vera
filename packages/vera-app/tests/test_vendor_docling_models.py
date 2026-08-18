"""Offline checks for the Docling vendor helper."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "vendor_docling_models.py"


def _load_vendor():
    spec = importlib.util.spec_from_file_location("vendor_docling_models", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_complete_snapshot(dest: Path, vendor) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for name in vendor.REQUIRED_FILES:
        path = dest / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"stub")


def test_snapshot_is_complete_requires_weights(tmp_path: Path):
    vendor = _load_vendor()
    dest = tmp_path / "docling-artifacts"
    dest.mkdir()
    assert vendor.snapshot_is_complete(dest) is False
    _write_complete_snapshot(dest, vendor)
    assert vendor.snapshot_is_complete(dest) is True
    vendor.verify_snapshot(dest)


def test_zero_byte_weights_are_not_complete(tmp_path: Path):
    vendor = _load_vendor()
    dest = tmp_path / "docling-artifacts"
    _write_complete_snapshot(dest, vendor)
    (dest / vendor.REQUIRED_FILES[-1]).write_bytes(b"")
    assert vendor.snapshot_is_complete(dest) is False
    with pytest.raises(SystemExit, match="missing"):
        vendor.verify_snapshot(dest)


def test_verify_snapshot_lists_missing_files(tmp_path: Path):
    vendor = _load_vendor()
    dest = tmp_path / "empty"
    dest.mkdir()
    with pytest.raises(SystemExit, match="missing"):
        vendor.verify_snapshot(dest)


def test_vendor_reuses_complete_snapshot_without_download(tmp_path: Path):
    vendor = _load_vendor()
    dest = tmp_path / "docling-artifacts"
    _write_complete_snapshot(dest, vendor)
    vendor.vendor_docling_models(dest)
    assert (dest / "vera-docling-manifest.json").is_file()


def test_vendor_copies_complete_seed_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    vendor = _load_vendor()
    seed = tmp_path / "seed"
    dest = tmp_path / "dest"
    _write_complete_snapshot(seed, vendor)
    monkeypatch.setenv("VERA_DOCLING_VENDOR_CACHE", str(seed))
    vendor.vendor_docling_models(dest)
    assert vendor.snapshot_is_complete(dest)
    assert (dest / "vera-docling-manifest.json").is_file()


def test_seed_cache_candidates_include_override_and_appdata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    vendor = _load_vendor()
    override = tmp_path / "override"
    appdata = tmp_path / "AppData"
    monkeypatch.setenv("VERA_DOCLING_VENDOR_CACHE", str(override))
    monkeypatch.setenv("APPDATA", str(appdata))
    assert vendor.seed_cache_candidates() == [
        override,
        appdata / "@vera" / "app" / "docling-artifacts",
        appdata / "VERA" / "docling-artifacts",
    ]
    monkeypatch.delenv("VERA_DOCLING_VENDOR_CACHE", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    assert vendor.seed_cache_candidates() == []


def test_copy_snapshot_omits_huggingface_cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    vendor = _load_vendor()
    seed = tmp_path / "seed"
    dest = tmp_path / "dest"
    _write_complete_snapshot(seed, vendor)
    cache = seed / vendor.LAYOUT_DIR / ".cache" / "huggingface"
    cache.mkdir(parents=True)
    (cache / "tmp").write_text("partial", encoding="utf-8")
    monkeypatch.setenv("VERA_DOCLING_VENDOR_CACHE", str(seed))
    vendor.vendor_docling_models(dest)
    assert vendor.snapshot_is_complete(dest)
    assert not (dest / vendor.LAYOUT_DIR / ".cache").exists()


def test_incomplete_seed_is_skipped_and_download_uses_pinned_revisions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    vendor = _load_vendor()
    seed = tmp_path / "seed"
    dest = tmp_path / "dest"
    seed.mkdir()
    monkeypatch.setenv("VERA_DOCLING_VENDOR_CACHE", str(seed))
    calls = []

    def fake_download(repo_id, revision, local_dir, allow_patterns):
        calls.append(
            {
                "repo_id": repo_id,
                "revision": revision,
                "local_dir": local_dir,
                "allow_patterns": allow_patterns,
            }
        )
        for name in vendor.REQUIRED_FILES:
            path = dest / name
            if path.is_relative_to(local_dir):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"stub")

    monkeypatch.setattr(vendor, "_download_snapshot", fake_download)
    vendor.vendor_docling_models(dest)

    assert [item["repo_id"] for item in calls] == [
        vendor.LAYOUT_REPO_ID,
        vendor.TABLEFORMER_REPO_ID,
    ]
    assert calls[0]["revision"] == vendor.LAYOUT_REVISION
    assert calls[1]["revision"] == vendor.TABLEFORMER_REVISION
    assert calls[0]["allow_patterns"] == vendor.LAYOUT_ALLOW_PATTERNS
    assert calls[1]["allow_patterns"] == vendor.TABLEFORMER_ALLOW_PATTERNS
    assert vendor.snapshot_is_complete(dest)
    assert (dest / "vera-docling-manifest.json").is_file()


def test_vendor_does_not_copy_dest_onto_itself(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    vendor = _load_vendor()
    dest = tmp_path / "docling-artifacts"
    dest.mkdir()
    monkeypatch.setenv("VERA_DOCLING_VENDOR_CACHE", str(dest))
    calls = []

    def fake_download(repo_id, revision, local_dir, allow_patterns):
        calls.append(repo_id)
        for name in vendor.REQUIRED_FILES:
            path = dest / name
            if path.is_relative_to(local_dir):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"stub")

    monkeypatch.setattr(vendor, "_download_snapshot", fake_download)
    vendor.vendor_docling_models(dest)
    assert calls == [vendor.LAYOUT_REPO_ID, vendor.TABLEFORMER_REPO_ID]
