"""Download all-MiniLM-L6-v2 into a local directory for the sidecar freeze.

Only the PyTorch Sentence Transformers files are fetched. ONNX, OpenVINO, TF,
and Rust snapshots stay on the Hub so the installer does not grow by hundreds
of megabytes.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO_ID = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_ID = "all-MiniLM-L6-v2"
# Pin installer contents. Bump when intentionally refreshing the bundled snapshot.
REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
ALLOW_PATTERNS = (
    "config.json",
    "config_sentence_transformers.json",
    "modules.json",
    "model.safetensors",
    "sentence_bert_config.json",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.txt",
    "1_Pooling/*",
    "README.md",
)
REQUIRED_FILES = (
    "config.json",
    "modules.json",
    "model.safetensors",
    "tokenizer.json",
    "1_Pooling/config.json",
)


def snapshot_is_complete(dest: Path) -> bool:
    return all((dest / name).is_file() for name in REQUIRED_FILES)


def verify_snapshot(dest: Path) -> None:
    missing = [name for name in REQUIRED_FILES if not (dest / name).is_file()]
    if missing:
        raise SystemExit(f"MiniLM snapshot missing {missing} in {dest}")


def write_manifest(dest: Path, revision: str) -> None:
    payload = {
        "repo_id": REPO_ID,
        "model_id": MODEL_ID,
        "revision": revision,
    }
    (dest / "vera-minilm-manifest.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def vendor_minilm(dest: Path, *, revision: str = REVISION) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    if snapshot_is_complete(dest):
        write_manifest(dest, revision)
        print(f"Using existing MiniLM snapshot at {dest}", file=sys.stderr)
        return dest
    from huggingface_hub import snapshot_download

    snapshot_download(
        repo_id=REPO_ID,
        revision=revision,
        local_dir=str(dest),
        allow_patterns=list(ALLOW_PATTERNS),
    )
    cache_dir = dest / ".cache"
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    verify_snapshot(dest)
    write_manifest(dest, revision)
    print(f"Vendored {REPO_ID}@{revision} into {dest}", file=sys.stderr)
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dest",
        required=True,
        help="Directory that will contain the all-MiniLM-L6-v2 snapshot",
    )
    parser.add_argument("--revision", default=REVISION)
    args = parser.parse_args(argv)
    vendor_minilm(Path(args.dest), revision=args.revision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
