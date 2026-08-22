"""Copy a verified ONNX MiniLM snapshot into the sidecar freeze directory.

Does not fetch Hub ``onnx/`` folders or PyTorch ``model.safetensors``. The
graph must come from ``export_minilm_onnx.py`` and pass ``compare_minilm_onnx.py``.
Refreshing MiniLM means: re-export, re-compare, bump revision + SHA in this file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

REPO_ID = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_ID = "all-MiniLM-L6-v2"
# Pin installer contents. Bump when intentionally refreshing the bundled snapshot.
REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
# Filled after a passing export+compare. Empty means "hash not pinned yet".
EXPECTED_MODEL_SHA256 = "ed86670e6cf4be770ffa4f84b0c6f9ef1de63c01bddcc05633a702e67ef33f98"
REQUIRED_FILES = (
    "model.onnx",
    "tokenizer.json",
    "config.json",
)
OPTIONAL_FILES = (
    "tokenizer_config.json",
    "special_tokens_map.json",
    "vocab.txt",
    "sentence_bert_config.json",
    "vera-minilm-manifest.json",
)
FORBIDDEN_FILES = (
    "model.safetensors",
    "pytorch_model.bin",
    "model.onnx_data",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_is_complete(dest: Path) -> bool:
    return all((dest / name).is_file() for name in REQUIRED_FILES)


def verify_snapshot(dest: Path, *, check_hash: bool = True) -> None:
    missing = [name for name in REQUIRED_FILES if not (dest / name).is_file()]
    if missing:
        raise SystemExit(f"MiniLM snapshot missing {missing} in {dest}")
    if check_hash and EXPECTED_MODEL_SHA256:
        digest = sha256_file(dest / "model.onnx")
        if digest != EXPECTED_MODEL_SHA256:
            raise SystemExit(
                f"MiniLM model.onnx sha256 {digest} does not match pinned "
                f"{EXPECTED_MODEL_SHA256}. Re-run export_minilm_onnx.py and "
                "compare_minilm_onnx.py, then bump EXPECTED_MODEL_SHA256."
            )


def write_manifest(dest: Path, *, revision: str, digest: str) -> None:
    payload = {
        "repo_id": REPO_ID,
        "model_id": MODEL_ID,
        "revision": revision,
        "model_onnx_sha256": digest,
        "inputs": ["input_ids", "attention_mask", "token_type_ids"],
        "outputs": ["last_hidden_state"],
        "max_seq_length": 256,
        "pooling": "mean",
        "normalize": "l2",
    }
    (dest / "vera-minilm-manifest.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def strip_non_onnx_artifacts(dest: Path) -> None:
    """Remove Hub PyTorch weights and export caches from a vendor directory."""
    if not dest.is_dir():
        return
    for name in FORBIDDEN_FILES:
        path = dest / name
        if path.is_file():
            path.unlink()
    export_src = dest / ".export-src"
    if export_src.exists():
        shutil.rmtree(export_src, ignore_errors=True)


def _copy_snapshot(source: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for name in (*REQUIRED_FILES, *OPTIONAL_FILES):
        src = source / name
        if src.is_file():
            shutil.copy2(src, dest / name)
    strip_non_onnx_artifacts(dest)


def default_export_cache() -> Path:
    return Path(__file__).resolve().parents[1] / "build" / "minilm-export" / MODEL_ID


def vendor_minilm(dest: Path, *, revision: str = REVISION, source: Path | None = None) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    strip_non_onnx_artifacts(dest)
    if snapshot_is_complete(dest):
        try:
            verify_snapshot(dest)
            digest = sha256_file(dest / "model.onnx")
            write_manifest(dest, revision=revision, digest=digest)
            print(f"Using existing MiniLM ONNX snapshot at {dest}", file=sys.stderr)
            return dest
        except SystemExit:
            if EXPECTED_MODEL_SHA256:
                raise

    candidates = []
    if source is not None:
        candidates.append(source)
    candidates.append(default_export_cache())
    for candidate in candidates:
        if snapshot_is_complete(candidate) and candidate.resolve() != dest.resolve():
            _copy_snapshot(candidate, dest)
            verify_snapshot(dest)
            digest = sha256_file(dest / "model.onnx")
            write_manifest(dest, revision=revision, digest=digest)
            print(f"Copied MiniLM ONNX snapshot from {candidate} to {dest}", file=sys.stderr)
            return dest

    try:
        from export_minilm_onnx import export_minilm_onnx
    except ImportError:
        export_path = Path(__file__).resolve().parent / "export_minilm_onnx.py"
        spec_name = "export_minilm_onnx"
        import importlib.util

        spec = importlib.util.spec_from_file_location(spec_name, export_path)
        if spec is None or spec.loader is None:
            raise SystemExit(
                "MiniLM ONNX snapshot is missing. Run "
                "packages/vera-app/scripts/export_minilm_onnx.py then "
                "compare_minilm_onnx.py."
            ) from None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        export_minilm_onnx = module.export_minilm_onnx

    export_dest = default_export_cache()
    export_minilm_onnx(export_dest, revision=revision)
    _copy_snapshot(export_dest, dest)
    verify_snapshot(dest)
    digest = sha256_file(dest / "model.onnx")
    write_manifest(dest, revision=revision, digest=digest)
    print(f"Vendored MiniLM ONNX snapshot into {dest}", file=sys.stderr)
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dest",
        required=True,
        help="Directory that will contain the all-MiniLM-L6-v2 ONNX snapshot",
    )
    parser.add_argument(
        "--source",
        default="",
        help="Optional already-exported snapshot to copy (must match EXPECTED_MODEL_SHA256)",
    )
    parser.add_argument("--revision", default=REVISION)
    args = parser.parse_args(argv)
    vendor_minilm(
        Path(args.dest),
        revision=args.revision,
        source=Path(args.source) if args.source else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
