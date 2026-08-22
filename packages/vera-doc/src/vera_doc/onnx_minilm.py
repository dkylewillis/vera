"""ONNX Runtime MiniLM embedder (Chroma-style in-process inference).

The stored archive identity remains ``sentence-transformers/all-MiniLM-L6-v2``.
This module only swaps the runtime: tokenizers + onnxruntime, mean pooling,
and L2 normalize to match Sentence Transformers ``encode(..., normalize_embeddings=True)``.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import Any

import numpy as np

BUNDLED_MINILM_MODEL_ID = "all-MiniLM-L6-v2"
BUNDLED_MINILM_DIRNAME = "sentence_transformers_models"
ONNX_MINILM_HOME_ENV = "VERA_ONNX_MINILM_HOME"
SENTENCE_TRANSFORMERS_HOME_ENV = "VERA_SENTENCE_TRANSFORMERS_HOME"
MINILM_MAX_SEQ_LENGTH = 256
MINILM_DIMENSION = 384
MINILM_HUB_NAME = f"sentence-transformers/{BUNDLED_MINILM_MODEL_ID}"
_L2_EPS = 1e-12
_POOL_EPS = 1e-9


def looks_like_onnx_minilm_model(path: Path) -> bool:
    """True when ``path`` contains an ONNX MiniLM graph and tokenizer."""
    if not path.is_dir():
        return False
    return (path / "model.onnx").is_file() and (path / "tokenizer.json").is_file()


def minilm_bundle_home() -> Path | None:
    """Return the directory that may contain a vendored MiniLM snapshot."""
    for env_name in (ONNX_MINILM_HOME_ENV, SENTENCE_TRANSFORMERS_HOME_ENV):
        env = os.environ.get(env_name, "").strip()
        if env:
            candidate = Path(env)
            if candidate.is_dir():
                return candidate
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bundled = Path(meipass) / BUNDLED_MINILM_DIRNAME
        if bundled.is_dir():
            return bundled
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        for bundled in (
            exe_dir / BUNDLED_MINILM_DIRNAME,
            exe_dir / "_internal" / BUNDLED_MINILM_DIRNAME,
        ):
            if bundled.is_dir():
                return bundled
    return None


def _short_model_id(model_id: str) -> str:
    short = model_id.strip()
    if short.startswith("sentence-transformers/"):
        return short[len("sentence-transformers/") :]
    if short.startswith("sentence-transformers:"):
        return short[len("sentence-transformers:") :]
    return short


def resolve_onnx_minilm_source(model_id: str = BUNDLED_MINILM_MODEL_ID) -> Path | None:
    """Return a local ONNX MiniLM snapshot directory, or None."""
    if _short_model_id(model_id) != BUNDLED_MINILM_MODEL_ID:
        return None
    home = minilm_bundle_home()
    if home is None:
        return None
    direct = home / BUNDLED_MINILM_MODEL_ID
    if looks_like_onnx_minilm_model(direct):
        return direct
    if home.name == BUNDLED_MINILM_MODEL_ID and looks_like_onnx_minilm_model(home):
        return home
    if looks_like_onnx_minilm_model(home):
        return home
    return None


def mean_pool(last_hidden_state: np.ndarray, attention_mask: np.ndarray) -> np.ndarray:
    """Mean-pool token embeddings with the attention mask (Sentence Transformers pooling)."""
    mask = np.expand_dims(attention_mask.astype(np.float32), -1)
    summed = np.sum(last_hidden_state * mask, axis=1)
    counts = np.clip(mask.sum(axis=1), a_min=_POOL_EPS, a_max=None)
    return summed / counts


def l2_normalize(vectors: np.ndarray) -> np.ndarray:
    """Row-wise L2 normalize, matching PyTorch ``F.normalize`` epsilon."""
    norm = np.linalg.norm(vectors, axis=1)
    norm = np.where(norm == 0.0, _L2_EPS, norm)
    return (vectors / norm[:, np.newaxis]).astype(np.float32)


def pad_encodings(
    encoded: list[Any],
    *,
    max_seq_length: int = MINILM_MAX_SEQ_LENGTH,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Truncate to ``max_seq_length`` and pad to the longest sequence in the batch."""
    ids_list: list[list[int]] = []
    mask_list: list[list[int]] = []
    for item in encoded:
        ids = list(item.ids)[:max_seq_length]
        mask = list(item.attention_mask)[:max_seq_length]
        if not ids:
            ids = [0]
            mask = [0]
        ids_list.append(ids)
        mask_list.append(mask)
    max_len = max(len(row) for row in ids_list)
    padded_ids = np.zeros((len(ids_list), max_len), dtype=np.int64)
    padded_mask = np.zeros((len(mask_list), max_len), dtype=np.int64)
    for index, (ids, mask) in enumerate(zip(ids_list, mask_list)):
        padded_ids[index, : len(ids)] = ids
        padded_mask[index, : len(mask)] = mask
    token_type_ids = np.zeros_like(padded_ids)
    return padded_ids, padded_mask, token_type_ids


class OnnxMiniLMEmbedder:
    """Local MiniLM embedder using ONNX Runtime. Archive identity stays Hub-style."""

    def __init__(
        self,
        model_name: str = MINILM_HUB_NAME,
        *,
        source: str | Path | None = None,
        device: str = "",
        batch_size: int = 32,
    ) -> None:
        import onnxruntime
        from tokenizers import Tokenizer

        self.model_name = model_name
        self.normalization = "l2"
        self.dimension = MINILM_DIMENSION
        self._embed_lock = threading.Lock()
        self._encode_batch_size = max(1, int(batch_size))
        snapshot = Path(source) if source is not None else resolve_onnx_minilm_source(model_name)
        if snapshot is None or not looks_like_onnx_minilm_model(snapshot):
            raise FileNotFoundError(
                "ONNX MiniLM snapshot not found (need model.onnx and tokenizer.json). "
                "Set VERA_ONNX_MINILM_HOME or vendor the verified graph."
            )
        self._snapshot = snapshot
        tokenizer = Tokenizer.from_file(str(snapshot / "tokenizer.json"))
        tokenizer.enable_truncation(max_length=MINILM_MAX_SEQ_LENGTH)
        self._tokenizer = tokenizer
        providers = _onnx_providers(device, onnxruntime)
        session_options = onnxruntime.SessionOptions()
        session_options.log_severity_level = 3
        session_options.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        self._session = onnxruntime.InferenceSession(
            str(snapshot / "model.onnx"),
            sess_options=session_options,
            providers=providers,
        )

    def embed(self, texts: list[str]) -> list[np.ndarray]:
        if not texts:
            return []
        vectors: list[np.ndarray] = []
        with self._embed_lock:
            for start in range(0, len(texts), self._encode_batch_size):
                batch = texts[start : start + self._encode_batch_size]
                encoded = [
                    self._tokenizer.encode(text if text is not None else "") for text in batch
                ]
                input_ids, attention_mask, token_type_ids = pad_encodings(encoded)
                feeds = {
                    "input_ids": input_ids,
                    "attention_mask": attention_mask,
                    "token_type_ids": token_type_ids,
                }
                input_names = {item.name for item in self._session.get_inputs()}
                feeds = {key: value for key, value in feeds.items() if key in input_names}
                outputs = self._session.run(None, feeds)
                last_hidden = _last_hidden_state(self._session, outputs)
                pooled = mean_pool(last_hidden, attention_mask)
                vectors.extend(l2_normalize(pooled))
        return vectors


def _last_hidden_state(session: Any, outputs: list[np.ndarray]) -> np.ndarray:
    names = [item.name for item in session.get_outputs()]
    if "last_hidden_state" in names:
        return outputs[names.index("last_hidden_state")]
    if "token_embeddings" in names:
        return outputs[names.index("token_embeddings")]
    return outputs[0]


def _onnx_providers(device: str, onnxruntime: Any) -> list[str]:
    requested = (device or "cpu").strip().lower() or "cpu"
    available = list(onnxruntime.get_available_providers())
    preferred: list[str] = []
    if requested in {"cuda", "gpu", "cudaexecutionprovider"}:
        if "CUDAExecutionProvider" in available:
            preferred.append("CUDAExecutionProvider")
    preferred.append("CPUExecutionProvider")
    return [name for name in preferred if name in available] or available


def sentence_transformers_available() -> bool:
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        return False
    return True


def onnxruntime_available() -> bool:
    try:
        import onnxruntime  # noqa: F401
    except ImportError:
        return False
    return True


def tokenizers_available() -> bool:
    try:
        import tokenizers  # noqa: F401
    except ImportError:
        return False
    return True


def onnx_minilm_deps_available() -> bool:
    """True when MiniLM can run on ONNX Runtime (not merely that onnxruntime exists).

    Docling's RapidOCR extra also installs ``onnxruntime``. Requiring tokenizers
    keeps that from blocking the Sentence Transformers MiniLM path.
    """
    return onnxruntime_available() and tokenizers_available()
