"""Compare VERA ONNX MiniLM vectors to Sentence Transformers encode().

Analog of chroma-core/onnx-embedding ``compare_onnx.py``. Fails unless every
fixture string has cosine similarity >= 0.9999 against
``SentenceTransformer.encode(..., normalize_embeddings=True)``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

MIN_COSINE = 0.9999
REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
FIXTURE_TEXTS = [
    "",
    "stormwater detention requirements",
    "The quick brown fox jumps over the lazy dog.",
    "section 4.2",
    "a " * 400,
]
BENCHMARK_TEXTS = [
    "how big should the pond be",
    "pipe sizing chart",
    "section 4.2 detention design",
    "x" * 5000,
]


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 1.0 if float(np.linalg.norm(a)) == 0.0 and float(np.linalg.norm(b)) == 0.0 else 0.0
    return float(np.dot(a, b) / denom)


def compare_minilm_onnx(
    snapshot: Path,
    *,
    texts: list[str] | None = None,
    goldens_out: Path | None = None,
) -> list[dict[str, object]]:
    from sentence_transformers import SentenceTransformer

    from vera_doc.onnx_minilm import MINILM_HUB_NAME, OnnxMiniLMEmbedder

    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    st_model = SentenceTransformer(
        "sentence-transformers/all-MiniLM-L6-v2",
        revision=REVISION,
        device="cpu",
    )
    onnx = OnnxMiniLMEmbedder(MINILM_HUB_NAME, source=snapshot, device="cpu", batch_size=8)
    samples = list(texts if texts is not None else FIXTURE_TEXTS)
    st_vectors = st_model.encode(samples, normalize_embeddings=True)
    onnx_vectors = onnx.embed(samples)
    rows: list[dict[str, object]] = []
    failures: list[str] = []
    for text, st_vec, onnx_vec in zip(samples, st_vectors, onnx_vectors, strict=True):
        score = _cosine(
            np.asarray(st_vec, dtype=np.float32), np.asarray(onnx_vec, dtype=np.float32)
        )
        rows.append(
            {
                "text": text,
                "cosine": score,
                "vector": [float(x) for x in np.asarray(onnx_vec, dtype=np.float32).tolist()],
            }
        )
        if score < MIN_COSINE:
            failures.append(f"cosine={score:.8f} for {text[:80]!r}")
    singles = [onnx.embed([text])[0] for text in samples]
    for text, batched, single in zip(samples, onnx_vectors, singles, strict=True):
        score = _cosine(np.asarray(batched, dtype=np.float32), np.asarray(single, dtype=np.float32))
        if score < MIN_COSINE:
            failures.append(f"batch/single cosine={score:.8f} for {text[:80]!r}")
    if goldens_out is not None:
        goldens_out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model_name": MINILM_HUB_NAME,
            "min_cosine": MIN_COSINE,
            "items": [{"text": row["text"], "vector": row["vector"]} for row in rows],
        }
        goldens_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if failures:
        raise SystemExit(
            "ONNX MiniLM drifted from Sentence Transformers:\n  " + "\n  ".join(failures)
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--snapshot", required=True, help="Directory with model.onnx and tokenizer.json"
    )
    parser.add_argument(
        "--goldens-out",
        default="",
        help="Optional JSON path for golden vectors (ONNX outputs after a passing compare)",
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Also compare extra long/paraphrase strings (not default CI)",
    )
    args = parser.parse_args(argv)
    texts = list(FIXTURE_TEXTS)
    if args.benchmark:
        texts.extend(BENCHMARK_TEXTS)
    rows = compare_minilm_onnx(
        Path(args.snapshot),
        texts=texts,
        goldens_out=Path(args.goldens_out) if args.goldens_out else None,
    )
    for row in rows:
        print(f"{row['cosine']:.8f}\t{row['text'][:60]!r}")
    print(
        f"ok {len(rows)} texts, min cosine {min(float(r['cosine']) for r in rows):.8f}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
