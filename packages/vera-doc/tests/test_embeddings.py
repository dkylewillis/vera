"""Unit tests for embedder registry, hashing, and vector serialization."""

import pytest

from vera_doc.embedder_descriptors import EmbedderDescriptor
from vera_doc.embeddings import (
    HashingEmbedder,
    HashingOptions,
    UnknownEmbeddingModelError,
    clear_embedder_cache,
    cosine_similarity,
    describe_embedder,
    deserialize_vector,
    get_embedder,
    list_embedder_load_errors,
    list_embedding_models,
    list_embedding_provider_descriptors,
    list_embedding_providers,
    parse_model_spec,
    preflight_embedder,
    register_embedder,
    reset_embedding_registry,
    serialize_vector,
    unregister_embedder,
)


class TestCosineSimilarity:
    def test_identical_vectors_return_one(self):
        import numpy as np

        v = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        assert pytest.approx(cosine_similarity(v, v), abs=1e-6) == 1.0

    def test_orthogonal_vectors_return_zero(self):
        import numpy as np

        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([0.0, 1.0], dtype=np.float32)
        assert pytest.approx(cosine_similarity(a, b), abs=1e-6) == 0.0

    def test_zero_vector_returns_zero(self):
        import numpy as np

        z = np.zeros(4, dtype=np.float32)
        v = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        assert cosine_similarity(z, v) == 0.0

    def test_both_zero_vectors_return_zero(self):
        import numpy as np

        z = np.zeros(4, dtype=np.float32)
        assert cosine_similarity(z, z) == 0.0


class TestHashingEmbedder:
    def test_dimension_matches_output(self):
        emb = HashingEmbedder(dimension=128)
        vecs = emb.embed(["hello world"])
        assert vecs[0].shape == (128,)

    def test_empty_text_list_returns_empty(self):
        emb = HashingEmbedder()
        assert emb.embed([]) == []

    def test_vectors_are_normalised(self):
        import numpy as np

        emb = HashingEmbedder()
        v = emb.embed(["some text here"])[0]
        assert pytest.approx(float(np.linalg.norm(v)), abs=1e-5) == 1.0

    def test_same_text_produces_same_vector(self):
        emb = HashingEmbedder()
        v1 = emb.embed(["deterministic test"])[0]
        v2 = emb.embed(["deterministic test"])[0]
        assert (v1 == v2).all()

    def test_different_texts_produce_different_vectors(self):
        emb = HashingEmbedder()
        v1 = emb.embed(["apples and oranges"])[0]
        v2 = emb.embed(["quantum mechanics theory"])[0]
        assert not (v1 == v2).all()


class TestGetEmbedder:
    def test_hashing_keyword_returns_hashing_embedder(self):
        e = get_embedder("hashing")
        assert isinstance(e, HashingEmbedder)
        assert e.model_name == "vera-hashing-384"

    def test_provider_model_id_spec(self):
        e = get_embedder("hashing:vera-hashing-384")
        assert isinstance(e, HashingEmbedder)
        assert e.model_name == "vera-hashing-384"

    def test_legacy_sentence_transformers_slash_spec(self):
        provider, model_id = parse_model_spec("sentence-transformers/all-MiniLM-L6-v2")
        assert provider == "sentence-transformers"
        assert model_id == "all-MiniLM-L6-v2"

    def test_colon_sentence_transformers_spec(self):
        provider, model_id = parse_model_spec("sentence-transformers:all-MiniLM-L6-v2")
        assert provider == "sentence-transformers"
        assert model_id == "all-MiniLM-L6-v2"

    def test_unknown_model_raises(self):
        with pytest.raises(UnknownEmbeddingModelError, match="Unknown embedding"):
            get_embedder("my-custom-model-xyz")

    def test_unknown_provider_raises_after_entry_point_scan(self):
        with pytest.raises(UnknownEmbeddingModelError, match="Unknown embedding provider"):
            get_embedder("not-a-real-provider:some-model")

    def test_register_custom_provider(self):
        def factory(model_id: str, **config):
            return HashingEmbedder(model_name=f"custom/{model_id or 'default'}")

        register_embedder("unit-test-custom", factory, replace=True)
        try:
            embedder = get_embedder("unit-test-custom:alpha")
            assert embedder.model_name == "custom/alpha"
            assert "unit-test-custom" in list_embedding_providers()
        finally:
            unregister_embedder("unit-test-custom")
            clear_embedder_cache()

    def test_register_embedder_decorator(self):
        @register_embedder("unit-test-decorator", replace=True)
        def factory(model_id: str, **config):
            return HashingEmbedder(model_name=f"decorated/{model_id}")

        try:
            embedder = get_embedder("unit-test-decorator:beta")
            assert embedder.model_name == "decorated/beta"
        finally:
            unregister_embedder("unit-test-decorator")
            clear_embedder_cache()

    def test_hashing_options_from_mapping(self):
        embedder = get_embedder("hashing", embedder_options={"dimension": 128})
        assert embedder.dimension == 128
        assert embedder.model_name == "vera-hashing-128"
        # Search-time resolve from the stored model_name recovers dimension.
        again = get_embedder("vera-hashing-128")
        assert again.dimension == 128
        assert again.model_name == "vera-hashing-128"
        with pytest.raises(ValueError, match="Unknown Hashing option"):
            get_embedder("hashing", embedder_options={"typo": 1})

    def test_hashing_options_enforces_dimension_bounds(self):
        assert HashingOptions.from_mapping({"dimension": 8}).dimension == 8
        assert HashingOptions.from_mapping({"dimension": 4096}).dimension == 4096
        assert HashingOptions.from_mapping({"dimension": 128}).dimension == 128
        with pytest.raises(ValueError, match="dimension must be between 8 and 4096"):
            HashingOptions.from_mapping({"dimension": 1})
        with pytest.raises(ValueError, match="dimension must be between 8 and 4096"):
            HashingOptions.from_mapping({"dimension": 99999})
        with pytest.raises(ValueError, match="dimension must be between 8 and 4096"):
            get_embedder("hashing", embedder_options={"dimension": 1})
        with pytest.raises(ValueError, match="dimension must be an integer"):
            HashingOptions.from_mapping({"dimension": True})
        with pytest.raises(ValueError, match="dimension must be an integer"):
            HashingOptions.from_mapping({"dimension": 8.9})
        with pytest.raises(ValueError, match="dimension must be a multiple of 8"):
            HashingOptions.from_mapping({"dimension": 9})

    def test_describe_builtin_providers(self):
        hashing = describe_embedder("hashing")
        assert hashing.provider == "hashing"
        assert hashing.field_keys() == {"dimension"}
        assert hashing.defaults()["dimension"] == 384
        assert hashing.always_fields()[0].key == "dimension"
        st = describe_embedder("sentence-transformers")
        assert {item.key for item in st.convert_fields()} == {"device", "batch_size"}
        descriptors = list_embedding_provider_descriptors()
        providers = {item.provider for item in descriptors}
        assert "hashing" in providers
        assert "sentence-transformers" in providers

    def test_list_embedding_models_and_preflight(self, monkeypatch):
        models = list_embedding_models("hashing")
        assert models[0].model_id == "vera-hashing-384"
        assert models[0].spec.startswith("hashing:")
        st_models = list_embedding_models("sentence-transformers")
        assert any(item.model_id == "all-MiniLM-L6-v2" for item in st_models)
        assert preflight_embedder("hashing").ok is True

        from vera_doc import EmbedderCapabilities, EmbedderDescriptor, register_embedder_descriptor

        @register_embedder("unit-test-creds", replace=True)
        def factory(model_id: str, **config):
            return HashingEmbedder(model_name=f"creds/{model_id}")

        register_embedder_descriptor(
            "unit-test-creds",
            lambda: EmbedderDescriptor(
                provider="unit-test-creds",
                label="creds",
                capabilities=EmbedderCapabilities(
                    requires_api_key=True,
                    credential_env="UNIT_TEST_EMBED_KEY",
                ),
            ),
            replace=True,
        )
        try:
            monkeypatch.delenv("UNIT_TEST_EMBED_KEY", raising=False)
            failed = preflight_embedder("unit-test-creds:alpha")
            assert failed.ok is False
            assert failed.missing_credential_env == "UNIT_TEST_EMBED_KEY"
            monkeypatch.setenv("UNIT_TEST_EMBED_KEY", "secret")
            assert preflight_embedder("unit-test-creds:alpha").ok is True
        finally:
            unregister_embedder("unit-test-creds")
            clear_embedder_cache()

    def test_config_keyed_cache(self):
        calls: list[tuple[str, dict]] = []

        def factory(model_id: str, **config):
            calls.append((model_id, dict(config)))
            return HashingEmbedder(
                dimension=int(config.get("dimension", 384)),
                model_name=f"cache-test/{model_id}",
            )

        register_embedder("cache-test", factory, replace=True)
        try:
            clear_embedder_cache()
            a = get_embedder("cache-test:one", dimension=128)
            b = get_embedder("cache-test:one", dimension=128)
            c = get_embedder("cache-test:one", dimension=256)
            assert a is b
            assert a is not c
            assert a.dimension == 128
            assert c.dimension == 256
            assert len(calls) == 2
        finally:
            unregister_embedder("cache-test")
            clear_embedder_cache()

    def test_entry_point_discovery(self, monkeypatch):
        class FakeEntry:
            name = "ep-test"

            def load(self):
                return lambda model_id, **config: HashingEmbedder(
                    model_name=f"ep/{model_id or 'default'}"
                )

        class FakeDescriptorEntry:
            name = "ep-test"

            def load(self):
                return lambda: EmbedderDescriptor(
                    provider="ep-test",
                    label="ep-test",
                    description="entry-point descriptor",
                )

        def fake_entry_points(*, group=None):
            if group == "vera.embedders":
                return [FakeEntry()]
            if group == "vera.embedder_descriptors":
                return [FakeDescriptorEntry()]
            if group == "vera.embedder_models":
                return []
            return []

        reset_embedding_registry(builtins=True)
        monkeypatch.setattr(
            "vera_doc.embeddings.entry_points",
            fake_entry_points,
        )
        try:
            embedder = get_embedder("ep-test:widget")
            assert embedder.model_name == "ep/widget"
            descriptor = describe_embedder("ep-test")
            assert descriptor.description == "entry-point descriptor"
        finally:
            reset_embedding_registry(builtins=True)

    def test_failing_entry_point_is_logged_and_not_registered(self, monkeypatch, caplog):
        import logging

        load_count = {"n": 0}

        class BrokenEntry:
            name = "broken-remote"

            def load(self):
                load_count["n"] += 1
                raise ImportError("native library missing")

        def fake_entry_points(*, group=None):
            if group == "vera.embedders":
                return [BrokenEntry()]
            return []

        reset_embedding_registry(builtins=True)
        monkeypatch.setattr(
            "vera_doc.embeddings.entry_points",
            fake_entry_points,
        )
        try:
            with caplog.at_level(logging.WARNING, logger="vera_doc.embeddings"):
                providers = list_embedding_providers()
            assert "broken-remote" not in providers
            assert "hashing" in providers
            warning_text = " ".join(
                record.getMessage()
                for record in caplog.records
                if record.levelno == logging.WARNING
            )
            assert "broken-remote" in warning_text
            assert "native library missing" in warning_text
            errors = list_embedder_load_errors()
            assert any(item["provider"] == "broken-remote" for item in errors)
            with pytest.raises(UnknownEmbeddingModelError, match="Plugin load errors"):
                get_embedder("broken-remote:unused")
            failed = preflight_embedder("broken-remote:unused")
            assert failed.ok is False
            assert "Plugin load errors" in failed.detail
            list_embedding_providers()
            assert load_count["n"] == 1
        finally:
            reset_embedding_registry(builtins=True)


class TestVectorSerialization:
    def test_round_trip_preserves_values(self):
        original = [1.5, -0.25, 3.0, 0.0]
        blob = serialize_vector(original)
        recovered = deserialize_vector(blob).tolist()
        assert recovered == pytest.approx(original, abs=1e-6)

    def test_serialization_produces_bytes(self):
        blob = serialize_vector([1.0, 2.0])
        assert isinstance(blob, bytes)

    def test_byte_length_is_four_per_float(self):
        blob = serialize_vector([0.0] * 10)
        assert len(blob) == 40  # 10 * 4 bytes (float32)


class TestEmbedderCacheConcurrency:
    def test_slow_factory_does_not_block_hashing_get_embedder(self):
        import threading
        import time

        started = threading.Event()
        release = threading.Event()

        def factory(model_id: str, **config):
            started.set()
            assert release.wait(timeout=5)
            return HashingEmbedder(model_name=f"slow/{model_id}")

        register_embedder("slow-block", factory, replace=True)
        clear_embedder_cache()
        try:
            worker = threading.Thread(target=lambda: get_embedder("slow-block:one"))
            worker.start()
            assert started.wait(timeout=2)
            t0 = time.perf_counter()
            embedder = get_embedder("hashing")
            elapsed = time.perf_counter() - t0
            assert elapsed < 1.0
            assert isinstance(embedder, HashingEmbedder)
            release.set()
            worker.join(timeout=5)
            assert not worker.is_alive()
        finally:
            release.set()
            unregister_embedder("slow-block")
            clear_embedder_cache()
