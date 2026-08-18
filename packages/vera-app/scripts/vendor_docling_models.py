"""Download Docling layout/table snapshots for the sidecar freeze.

Prefetch matches the converter: Heron ONNX plus TableFormer accurate only.
Transformers Heron, TableFormer fast, and other Docling Hub extras stay on
the Hub so the installer does not grow by another several hundred megabytes.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

LAYOUT_REPO_ID = "docling-project/docling-layout-heron-onnx"
LAYOUT_DIR = "docling-project--docling-layout-heron-onnx"
# Pin installer contents. Bump when intentionally refreshing the bundled snapshot.
LAYOUT_REVISION = "40bde044036bb181c130ddf6c51792187268748f"
LAYOUT_ALLOW_PATTERNS = (
    "config.json",
    "model.onnx",
    "preprocessor_config.json",
    "README.md",
)

TABLEFORMER_REPO_ID = "docling-project/docling-models"
TABLEFORMER_DIR = "docling-project--docling-models"
TABLEFORMER_REVISION = "fc0f2d45e2218ea24bce5045f58a389aed16dc23"
TABLEFORMER_ALLOW_PATTERNS = (
    "model_artifacts/tableformer/accurate/**",
    "config.json",
    "README.md",
    ".gitattributes",
    ".gitignore",
)

REQUIRED_FILES = (
    f"{LAYOUT_DIR}/config.json",
    f"{LAYOUT_DIR}/model.onnx",
    f"{LAYOUT_DIR}/preprocessor_config.json",
    f"{TABLEFORMER_DIR}/model_artifacts/tableformer/accurate/tm_config.json",
    f"{TABLEFORMER_DIR}/model_artifacts/tableformer/accurate/tableformer_accurate.safetensors",
)


def snapshot_is_complete(dest: Path) -> bool:
    return all(
        (dest / name).is_file() and (dest / name).stat().st_size > 0 for name in REQUIRED_FILES
    )


def verify_snapshot(dest: Path) -> None:
    missing = [
        name
        for name in REQUIRED_FILES
        if not ((dest / name).is_file() and (dest / name).stat().st_size > 0)
    ]
    if missing:
        raise SystemExit(f"Docling snapshot missing {missing} in {dest}")


def write_manifest(dest: Path) -> None:
    payload = {
        "layout_repo_id": LAYOUT_REPO_ID,
        "layout_revision": LAYOUT_REVISION,
        "tableformer_repo_id": TABLEFORMER_REPO_ID,
        "tableformer_revision": TABLEFORMER_REVISION,
    }
    (dest / "vera-docling-manifest.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def _strip_hf_cache(directory: Path) -> None:
    cache_dir = directory / ".cache"
    if cache_dir.exists():
        shutil.rmtree(cache_dir)


def seed_cache_candidates() -> list[Path]:
    """Local complete caches that can seed the installer without a Hub download."""
    candidates: list[Path] = []
    env = (os.environ.get("VERA_DOCLING_VENDOR_CACHE") or "").strip()
    if env:
        candidates.append(Path(env))
    appdata = (os.environ.get("APPDATA") or "").strip()
    if appdata:
        root = Path(appdata)
        candidates.append(root / "@vera" / "app" / "docling-artifacts")
        candidates.append(root / "VERA" / "docling-artifacts")
    return candidates


def _copy_snapshot_trees(src: Path, dest: Path) -> None:
    for relative in (LAYOUT_DIR, TABLEFORMER_DIR):
        source = src / relative
        target = dest / relative
        if not source.is_dir():
            continue
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target, ignore=shutil.ignore_patterns(".cache"))
    _strip_hf_cache(dest)


def _seed_from_existing_cache(dest: Path) -> bool:
    for candidate in seed_cache_candidates():
        if candidate.resolve() == dest.resolve():
            continue
        if not snapshot_is_complete(candidate):
            continue
        print(f"Copying Docling snapshot from {candidate}", file=sys.stderr)
        _copy_snapshot_trees(candidate, dest)
        return snapshot_is_complete(dest)
    return False


def _download_snapshot(
    repo_id: str,
    revision: str,
    local_dir: Path,
    allow_patterns: tuple[str, ...],
) -> None:
    from huggingface_hub import snapshot_download

    local_dir.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {repo_id}@{revision}...", file=sys.stderr, flush=True)
    snapshot_download(
        repo_id=repo_id,
        revision=revision,
        local_dir=str(local_dir),
        allow_patterns=list(allow_patterns),
    )
    _strip_hf_cache(local_dir)


def vendor_docling_models(dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    if snapshot_is_complete(dest):
        write_manifest(dest)
        print(f"Using existing Docling snapshot at {dest}", file=sys.stderr)
        return dest
    if _seed_from_existing_cache(dest):
        write_manifest(dest)
        print(f"Using copied Docling snapshot at {dest}", file=sys.stderr)
        return dest
    _download_snapshot(
        LAYOUT_REPO_ID,
        LAYOUT_REVISION,
        dest / LAYOUT_DIR,
        LAYOUT_ALLOW_PATTERNS,
    )
    _download_snapshot(
        TABLEFORMER_REPO_ID,
        TABLEFORMER_REVISION,
        dest / TABLEFORMER_DIR,
        TABLEFORMER_ALLOW_PATTERNS,
    )
    _strip_hf_cache(dest)
    verify_snapshot(dest)
    write_manifest(dest)
    print(
        f"Vendored {LAYOUT_REPO_ID}@{LAYOUT_REVISION} and "
        f"{TABLEFORMER_REPO_ID}@{TABLEFORMER_REVISION} into {dest}",
        file=sys.stderr,
    )
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dest",
        required=True,
        help="Directory that will contain Docling layout and table snapshots",
    )
    args = parser.parse_args(argv)
    vendor_docling_models(Path(args.dest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
