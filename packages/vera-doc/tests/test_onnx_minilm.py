"""ONNX MiniLM snapshot detection, pooling, and optional golden-vector checks."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest

from vera_doc import ChunkRecord, VeraDocument
from vera_doc.embeddings import (
    BUNDLED_MINILM_MODEL_ID,
    SENTENCE_TRANSFORMERS_HOME_ENV,
    UnknownEmbeddingModelError,
    bundled_minilm_available,
    clear_embedder_cache,
    cosine_similarity,
    describe_embedder,
    get_embedder,
    list_embedding_models,
)
from vera_doc.onnx_minilm import (
    BUNDLED_MINILM_DIRNAME,
    MINILM_HUB_NAME,
    MINILM_MAX_SEQ_LENGTH,
    ONNX_MINILM_HOME_ENV,
    OnnxMiniLMEmbedder,
    l2_normalize,
    looks_like_onnx_minilm_model,
    mean_pool,
    pad_encodings,
    resolve_onnx_minilm_source,
    sentence_transformers_available,
)

_GOLDENS = Path(__file__).resolve().parent / "data" / "minilm_onnx_goldens.json"
_REPO_SNAPSHOT = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "vera-app"
    / "build"
    / "minilm"
    / "all-MiniLM-L6-v2"
)


def _onnx_snapshot() -> Path | None:
    env = os.environ.get(ONNX_MINILM_HOME_ENV, "").strip()
    if env:
        direct = Path(env) / BUNDLED_MINILM_MODEL_ID
        if looks_like_onnx_minilm_model(direct):
            return direct
        if looks_like_onnx_minilm_model(Path(env)):
            return Path(env)
    if looks_like_onnx_minilm_model(_REPO_SNAPSHOT):
        return _REPO_SNAPSHOT
    return resolve_onnx_minilm_source(BUNDLED_MINILM_MODEL_ID)


class TestOnnxSnapshotDetection:
    def test_rejects_incomplete_snapshot(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        assert looks_like_onnx_minilm_model(empty) is False
        (empty / "tokenizer.json").write_text("{}", encoding="utf-8")
        assert looks_like_onnx_minilm_model(empty) is False

    def test_accepts_onnx_and_tokenizer(self, tmp_path):
        model_dir = tmp_path / BUNDLED_MINILM_MODEL_ID
        model_dir.mkdir()
        (model_dir / "model.onnx").write_bytes(b"stub")
        (model_dir / "tokenizer.json").write_text("{}", encoding="utf-8")
        assert looks_like_onnx_minilm_model(model_dir) is True

    def test_resolves_from_onnx_home_env(self, tmp_path, monkeypatch):
        model_dir = tmp_path / BUNDLED_MINILM_MODEL_ID
        model_dir.mkdir()
        (model_dir / "model.onnx").write_bytes(b"stub")
        (model_dir / "tokenizer.json").write_text("{}", encoding="utf-8")
        monkeypatch.setenv(ONNX_MINILM_HOME_ENV, str(tmp_path))
        monkeypatch.delenv(SENTENCE_TRANSFORMERS_HOME_ENV, raising=False)
        assert resolve_onnx_minilm_source(BUNDLED_MINILM_MODEL_ID) == model_dir
        assert bundled_minilm_available() is True
        assert describe_embedder("sentence-transformers").capabilities.requires_network is False

    def test_st_alias_env_still_finds_onnx_snapshot(self, tmp_path, monkeypatch):
        model_dir = tmp_path / BUNDLED_MINILM_MODEL_ID
        model_dir.mkdir()
        (model_dir / "model.onnx").write_bytes(b"stub")
        (model_dir / "tokenizer.json").write_text("{}", encoding="utf-8")
        monkeypatch.delenv(ONNX_MINILM_HOME_ENV, raising=False)
        monkeypatch.setenv(SENTENCE_TRANSFORMERS_HOME_ENV, str(tmp_path))
        assert resolve_onnx_minilm_source(MINILM_HUB_NAME) == model_dir


class TestPooling:
    def test_mean_pool_ignores_padded_tokens(self):
        hidden = np.array(
            [[[1.0, 1.0], [10.0, 10.0], [100.0, 100.0]]],
            dtype=np.float32,
        )
        mask = np.array([[1, 1, 0]], dtype=np.int64)
        pooled = mean_pool(hidden, mask)
        assert pooled.shape == (1, 2)
        np.testing.assert_allclose(pooled[0], [5.5, 5.5], atol=1e-6)

    def test_l2_normalize_unit_length(self):
        vectors = np.array([[3.0, 4.0], [0.0, 0.0]], dtype=np.float32)
        out = l2_normalize(vectors)
        assert pytest.approx(float(np.linalg.norm(out[0])), abs=1e-6) == 1.0
        # Zero rows stay zero after divide-by-eps, matching F.normalize.
        assert pytest.approx(float(np.linalg.norm(out[1])), abs=1e-6) == 0.0

    def test_pad_encodings_truncates_to_256(self):
        class _Enc:
            def __init__(self, length: int) -> None:
                self.ids = list(range(length))
                self.attention_mask = [1] * length

        ids, mask, token_types = pad_encodings([_Enc(400)])
        assert ids.shape == (1, MINILM_MAX_SEQ_LENGTH)
        assert mask.shape == ids.shape
        assert token_types.shape == ids.shape
        assert int(ids[0, -1]) == MINILM_MAX_SEQ_LENGTH - 1
        assert int(mask.sum()) == MINILM_MAX_SEQ_LENGTH

    def test_pad_encodings_handles_empty(self):
        class _Enc:
            def __init__(self) -> None:
                self.ids: list[int] = []
                self.attention_mask: list[int] = []

        ids, mask, token_types = pad_encodings([_Enc()])
        assert ids.shape == (1, 1)
        assert int(ids[0, 0]) == 0
        assert int(mask[0, 0]) == 0
        assert int(token_types[0, 0]) == 0


class TestFrozenOnnxSnapshot:
    def test_frozen_sidecar_detects_onnx_snapshot(self, tmp_path, monkeypatch):
        exe_dir = tmp_path / "app"
        exe_dir.mkdir()
        exe = exe_dir / "vera-sidecar"
        exe.write_bytes(b"")
        model_dir = exe_dir / "_internal" / BUNDLED_MINILM_DIRNAME / BUNDLED_MINILM_MODEL_ID
        model_dir.mkdir(parents=True)
        (model_dir / "model.onnx").write_bytes(b"stub")
        (model_dir / "tokenizer.json").write_text("{}", encoding="utf-8")
        monkeypatch.delenv(ONNX_MINILM_HOME_ENV, raising=False)
        monkeypatch.delenv(SENTENCE_TRANSFORMERS_HOME_ENV, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "missing-meipass"), raising=False)
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable", str(exe))
        assert resolve_onnx_minilm_source(BUNDLED_MINILM_MODEL_ID) == model_dir
        assert bundled_minilm_available() is True
        assert describe_embedder("sentence-transformers").capabilities.requires_network is False


class TestModelListing:
    def test_minilm_l6_is_always_listed(self):
        models = list_embedding_models("sentence-transformers")
        assert any(item.model_id == "all-MiniLM-L6-v2" for item in models)
        ids = {item.model_id for item in models}
        if sentence_transformers_available():
            assert "all-MiniLM-L12-v2" in ids
        else:
            assert "all-MiniLM-L12-v2" not in ids

    def test_minilm_falls_back_to_st_when_no_onnx_graph_is_present(self, tmp_path, monkeypatch):
        pytest.importorskip("onnxruntime")
        pytest.importorskip("tokenizers")
        pytest.importorskip("sentence_transformers")
        monkeypatch.delenv(ONNX_MINILM_HOME_ENV, raising=False)
        monkeypatch.setenv(SENTENCE_TRANSFORMERS_HOME_ENV, str(tmp_path))
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "missing-meipass"), raising=False)

        class DummySentenceTransformer:
            model_name = MINILM_HUB_NAME

            def __init__(self, *args, **kwargs) -> None:
                pass

            def embed(self, texts: list[str]) -> list[np.ndarray]:
                return []

        monkeypatch.setattr(
            "vera_doc.embeddings.SentenceTransformerEmbedder", DummySentenceTransformer
        )
        clear_embedder_cache()
        embedder = get_embedder("sentence-transformers:all-MiniLM-L6-v2")
        assert isinstance(embedder, DummySentenceTransformer)

    def test_minilm_error_names_both_extras_when_no_runtime_is_available(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.delenv(ONNX_MINILM_HOME_ENV, raising=False)
        monkeypatch.setenv(SENTENCE_TRANSFORMERS_HOME_ENV, str(tmp_path))
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "missing-meipass"), raising=False)

        def missing(*args, **kwargs):
            raise ImportError("sentence-transformers is not installed")

        monkeypatch.setattr("vera_doc.embeddings.SentenceTransformerEmbedder", missing)
        clear_embedder_cache()
        with pytest.raises(UnknownEmbeddingModelError, match=r"vera-doc\[ml\]"):
            get_embedder("sentence-transformers:all-MiniLM-L6-v2")

    def test_minilm_factory_uses_onnx_when_snapshot_exists(self, tmp_path, monkeypatch, capsys):
        model_dir = tmp_path / BUNDLED_MINILM_MODEL_ID
        model_dir.mkdir()
        (model_dir / "model.onnx").write_bytes(b"stub")
        (model_dir / "tokenizer.json").write_text("{}", encoding="utf-8")
        monkeypatch.setenv(ONNX_MINILM_HOME_ENV, str(tmp_path))
        monkeypatch.delenv(SENTENCE_TRANSFORMERS_HOME_ENV, raising=False)

        class DummyOnnx:
            model_name = MINILM_HUB_NAME

            def __init__(self, *args, **kwargs) -> None:
                pass

            def embed(self, texts: list[str]) -> list[np.ndarray]:
                return []

        def boom(*args, **kwargs):
            raise AssertionError(
                "Sentence Transformers should not load MiniLM when an ONNX snapshot exists"
            )

        monkeypatch.setattr("vera_doc.embeddings.OnnxMiniLMEmbedder", DummyOnnx)
        monkeypatch.setattr("vera_doc.embeddings.SentenceTransformerEmbedder", boom)
        clear_embedder_cache()
        embedder = get_embedder("sentence-transformers:all-MiniLM-L6-v2")
        assert isinstance(embedder, DummyOnnx)
        assert "MiniLM runtime=onnx" in capsys.readouterr().err


@pytest.mark.skipif(_onnx_snapshot() is None, reason="vendored MiniLM ONNX snapshot is not present")
class TestOnnxMiniLMGoldens:
    def test_goldens_match_onnx_embedder(self, monkeypatch, capsys):
        snapshot = _onnx_snapshot()
        assert snapshot is not None
        pytest.importorskip("onnxruntime")
        pytest.importorskip("tokenizers")
        monkeypatch.setenv(ONNX_MINILM_HOME_ENV, str(snapshot.parent))
        clear_embedder_cache()
        embedder = get_embedder("sentence-transformers:all-MiniLM-L6-v2")
        assert isinstance(embedder, OnnxMiniLMEmbedder)
        assert embedder.model_name == MINILM_HUB_NAME
        assert "MiniLM runtime=onnx" in capsys.readouterr().err
        payload = json.loads(_GOLDENS.read_text(encoding="utf-8"))
        texts = [item["text"] for item in payload["items"]]
        vectors = embedder.embed(texts)
        for item, vector in zip(payload["items"], vectors, strict=True):
            expected = np.asarray(item["vector"], dtype=np.float32)
            score = cosine_similarity(vector, expected)
            assert score >= 0.9999, item["text"][:80]


def _load_compare_module():
    path = (
        Path(__file__).resolve().parents[3]
        / "packages"
        / "vera-app"
        / "scripts"
        / "compare_minilm_onnx.py"
    )
    spec = importlib.util.spec_from_file_location("compare_minilm_onnx", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(_onnx_snapshot() is None, reason="vendored MiniLM ONNX snapshot is not present")
class TestLiveSentenceTransformersParity:
    def test_compare_script_cosine_threshold(self):
        snapshot = _onnx_snapshot()
        assert snapshot is not None
        pytest.importorskip("sentence_transformers")
        pytest.importorskip("onnxruntime")
        pytest.importorskip("tokenizers")
        compare = _load_compare_module()
        rows = compare.compare_minilm_onnx(snapshot)
        assert min(float(row["cosine"]) for row in rows) >= 0.9999

    def test_onnx_and_st_same_semantic_topk(self, tmp_path, monkeypatch):
        snapshot = _onnx_snapshot()
        assert snapshot is not None
        pytest.importorskip("sentence_transformers")
        pytest.importorskip("onnxruntime")
        pytest.importorskip("tokenizers")
        monkeypatch.setenv(ONNX_MINILM_HOME_ENV, str(snapshot.parent))
        clear_embedder_cache()
        onnx_path = tmp_path / "onnx.vera"
        storm = "Stormwater detention ponds store the 100-year runoff volume."
        bike = "Bicycle lane striping uses thermoplastic paint on asphalt."
        with VeraDocument.create(
            onnx_path, model="sentence-transformers:all-MiniLM-L6-v2"
        ) as document:
            assert isinstance(document._embedding_function, OnnxMiniLMEmbedder)
            document.add(
                [
                    ChunkRecord(id="storm", text=storm),
                    ChunkRecord(id="bike", text=bike),
                ]
            )
        with VeraDocument.open(onnx_path) as document:
            hits = document.search(text="detention pond storage", mode="semantic", top_k=2)
        assert hits[0].record.id == "storm"

        from vera_doc.embeddings import SentenceTransformerEmbedder

        st_path = tmp_path / "st.vera"
        with VeraDocument.create(
            st_path,
            embedding_function=SentenceTransformerEmbedder(MINILM_HUB_NAME),
        ) as document:
            document.add(
                [
                    ChunkRecord(id="storm", text=storm),
                    ChunkRecord(id="bike", text=bike),
                ]
            )
        with VeraDocument.open(st_path) as document:
            st_hits = document.search(text="detention pond storage", mode="semantic", top_k=2)
        assert st_hits[0].record.id == hits[0].record.id
