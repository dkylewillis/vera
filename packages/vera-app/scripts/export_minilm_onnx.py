"""Export a VERA-owned fp32 ONNX graph for all-MiniLM-L6-v2.

This script requires the workspace ``ml`` extra plus the ``onnx`` package
(``uv sync --extra ml``). Do not vendor Hub ``onnx/`` folders — output names
differ. After a passing compare, bump ``EXPECTED_MODEL_SHA256`` in
``vendor_minilm.py``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ID = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_ID = "all-MiniLM-L6-v2"
REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
MAX_SEQ_LENGTH = 256
REQUIRED_COPIES = (
    "config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "vocab.txt",
    "sentence_bert_config.json",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_sentence_transformer(cache_dir: Path):
    from huggingface_hub import snapshot_download
    from sentence_transformers import SentenceTransformer

    snapshot = snapshot_download(
        repo_id=REPO_ID,
        revision=REVISION,
        local_dir=str(cache_dir),
        allow_patterns=[
            "config.json",
            "config_sentence_transformers.json",
            "modules.json",
            "model.safetensors",
            "pytorch_model.bin",
            "sentence_bert_config.json",
            "special_tokens_map.json",
            "tokenizer.json",
            "tokenizer_config.json",
            "vocab.txt",
            "1_Pooling/*",
            "README.md",
        ],
    )
    return SentenceTransformer(snapshot, device="cpu"), Path(snapshot)


def export_minilm_onnx(dest: Path, *, revision: str = REVISION) -> Path:
    """Export last_hidden_state ONNX + tokenizer files into ``dest``."""
    dest.mkdir(parents=True, exist_ok=True)
    onnx_path = dest / "model.onnx"
    # Keep Hub PyTorch weights out of dest so freeze --add-data cannot pick them up.
    with tempfile.TemporaryDirectory(prefix="vera-minilm-export-") as tmp:
        model, snapshot = _load_sentence_transformer(Path(tmp))

        import torch
        import torch.nn as nn

        transformer = model[0].auto_model
        transformer.eval()

        class _LastHidden(nn.Module):
            def __init__(self, inner: nn.Module) -> None:
                super().__init__()
                self.inner = inner

            def forward(self, input_ids, attention_mask, token_type_ids):
                out = self.inner(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    token_type_ids=token_type_ids,
                )
                return out.last_hidden_state

        wrapped = _LastHidden(transformer)
        dummy_ids = torch.ones((1, MAX_SEQ_LENGTH), dtype=torch.long)
        dummy_mask = torch.ones((1, MAX_SEQ_LENGTH), dtype=torch.long)
        dummy_types = torch.zeros((1, MAX_SEQ_LENGTH), dtype=torch.long)
        torch.onnx.export(
            wrapped,
            (dummy_ids, dummy_mask, dummy_types),
            str(onnx_path),
            input_names=["input_ids", "attention_mask", "token_type_ids"],
            output_names=["last_hidden_state"],
            dynamic_axes={
                "input_ids": {0: "batch", 1: "sequence"},
                "attention_mask": {0: "batch", 1: "sequence"},
                "token_type_ids": {0: "batch", 1: "sequence"},
                "last_hidden_state": {0: "batch", 1: "sequence"},
            },
            opset_version=14,
            dynamo=False,
        )
        for name in REQUIRED_COPIES:
            src = snapshot / name
            if src.is_file():
                shutil.copy2(src, dest / name)

    digest = sha256_file(onnx_path)
    payload = {
        "repo_id": REPO_ID,
        "model_id": MODEL_ID,
        "revision": revision,
        "model_onnx_sha256": digest,
        "inputs": ["input_ids", "attention_mask", "token_type_ids"],
        "outputs": ["last_hidden_state"],
        "max_seq_length": MAX_SEQ_LENGTH,
        "pooling": "mean",
        "normalize": "l2",
    }
    (dest / "vera-minilm-manifest.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Exported {REPO_ID}@{revision} to {dest}", file=sys.stderr)
    print(f"model.onnx sha256={digest}", file=sys.stderr)
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dest",
        required=True,
        help="Directory that will contain model.onnx, tokenizer.json, and the manifest",
    )
    parser.add_argument("--revision", default=REVISION)
    args = parser.parse_args(argv)
    export_minilm_onnx(Path(args.dest), revision=args.revision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
