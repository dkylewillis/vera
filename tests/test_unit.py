"""Unit tests for individual modules (no PDF file required for most cases)."""

import pytest

from vera_ingest.chunking import chunk_pages, detect_heading
from vera.core.embeddings import (
    HashingEmbedder,
    UnknownEmbeddingModelError,
    clear_embedder_cache,
    cosine_similarity,
    describe_embedder,
    deserialize_vector,
    get_embedder,
    list_embedding_provider_descriptors,
    list_embedding_providers,
    parse_model_spec,
    register_embedder,
    reset_embedding_registry,
    serialize_vector,
    unregister_embedder,
)
from vera.core.embedder_descriptors import EmbedderDescriptor
from vera import ChunkRecord, QueryResult, VeraDocument
from vera_cli import str_to_bool
from vera_ingest.types import ParsedPage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pages(*texts: str) -> list[ParsedPage]:
    """Build a list of ParsedPage objects from plain strings."""
    return [ParsedPage(page_number=i + 1, width=612.0, height=792.0, text=t)
            for i, t in enumerate(texts)]


# ---------------------------------------------------------------------------
# chunk_pages
# ---------------------------------------------------------------------------

class TestChunkPages:
    def test_empty_pages_returns_no_chunks(self):
        assert chunk_pages([]) == []

    def test_invalid_chunk_size_raises(self):
        with pytest.raises(ValueError, match="chunk_size must be positive"):
            chunk_pages(_pages("hello world"), chunk_size=0)

    def test_negative_chunk_size_raises(self):
        with pytest.raises(ValueError, match="chunk_size must be positive"):
            chunk_pages(_pages("hello world"), chunk_size=-1)

    def test_page_with_empty_text_produces_no_chunks(self):
        assert chunk_pages(_pages("")) == []

    def test_page_with_only_whitespace_produces_no_chunks(self):
        assert chunk_pages(_pages("   \n\n  ")) == []

    def test_short_text_produces_one_chunk(self):
        chunks = chunk_pages(_pages("The quick brown fox."), chunk_size=500)
        assert len(chunks) == 1
        assert "fox" in chunks[0].text

    def test_chunk_page_numbers_are_preserved(self):
        chunks = chunk_pages(_pages("Page one text.", "Page two text."), chunk_size=500)
        page_numbers = {c.page_start for c in chunks}
        assert 1 in page_numbers
        assert 2 in page_numbers

    def test_large_paragraph_is_split_into_multiple_chunks(self):
        # 120 words > chunk_size=10
        words = " ".join(f"word{i}" for i in range(120))
        chunks = chunk_pages(_pages(words), chunk_size=10, overlap=2)
        assert len(chunks) > 1

    def test_overlap_is_clamped_to_chunk_size_minus_one(self):
        # overlap >= chunk_size should be clamped rather than crash
        words = " ".join(f"w{i}" for i in range(30))
        chunks = chunk_pages(_pages(words), chunk_size=5, overlap=10)
        assert len(chunks) >= 1

    def test_all_chunks_have_positive_token_count(self):
        text = " ".join(f"token{i}" for i in range(50))
        chunks = chunk_pages(_pages(text), chunk_size=10, overlap=2)
        for c in chunks:
            assert c.token_count > 0

    def test_heading_detected_from_chapter_line(self):
        text = "Chapter 3 Land Use\nSome content about land use regulations."
        chunks = chunk_pages(_pages(text), chunk_size=500)
        assert any("chapter" in (c.heading_path or "").lower() for c in chunks)

    def test_heading_detected_from_section_line(self):
        text = "Section 4.2 Zoning Districts\nContent describing the districts."
        chunks = chunk_pages(_pages(text), chunk_size=500)
        assert any("section" in (c.heading_path or "").lower() for c in chunks)

    def test_no_heading_uses_empty_string(self):
        chunks = chunk_pages(_pages("Just some plain text with no heading."), chunk_size=500)
        assert chunks[0].heading_path == ""


# ---------------------------------------------------------------------------
# detect_heading
# ---------------------------------------------------------------------------

class TestDetectHeading:
    def test_chapter_line_detected(self):
        result = detect_heading("Chapter 1 Introduction\nText here.", "")
        assert "Chapter" in result

    def test_non_heading_line_returns_current(self):
        result = detect_heading("This is just a sentence.", "current heading")
        assert result == "current heading"

    def test_very_long_line_is_not_a_heading(self):
        long_line = "word " * 30  # > 120 chars
        result = detect_heading(long_line.strip(), "old heading")
        assert result == "old heading"


# ---------------------------------------------------------------------------
# cosine_similarity
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# HashingEmbedder
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# get_embedder / registry
# ---------------------------------------------------------------------------

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
        with pytest.raises(ValueError, match="Unknown Hashing option"):
            get_embedder("hashing", embedder_options={"typo": 1})

    def test_describe_builtin_providers(self):
        hashing = describe_embedder("hashing")
        assert hashing.provider == "hashing"
        assert hashing.field_keys() == {"dimension"}
        assert hashing.defaults()["dimension"] == 384
        descriptors = list_embedding_provider_descriptors()
        providers = {item.provider for item in descriptors}
        assert "hashing" in providers
        assert "sentence-transformers" in providers

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
            return []

        reset_embedding_registry(builtins=True)
        monkeypatch.setattr(
            "vera.core.embeddings.entry_points",
            fake_entry_points,
        )
        try:
            embedder = get_embedder("ep-test:widget")
            assert embedder.model_name == "ep/widget"
            descriptor = describe_embedder("ep-test")
            assert descriptor.description == "entry-point descriptor"
        finally:
            reset_embedding_registry(builtins=True)


# ---------------------------------------------------------------------------
# serialize / deserialize vector round-trip
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# QueryResult
# ---------------------------------------------------------------------------

class TestQueryResult:
    def _make(self, **kwargs):
        defaults = dict(
            record=ChunkRecord(
                id="c001",
                text="Sample text",
                metadata={"page_start": 1},
            ),
            score=0.85,
        )
        defaults.update(kwargs)
        return QueryResult(**defaults)

    def test_as_dict_contains_all_fields(self):
        r = self._make()
        d = r.as_dict()
        assert d["chunk_id"] == "c001"
        assert d["score"] == pytest.approx(0.85)
        assert d["text"] == "Sample text"
        assert d["metadata"]["page_start"] == 1

    def test_as_dict_is_a_copy(self):
        r = self._make()
        d = r.as_dict()
        d["score"] = 0.0
        assert r.score == pytest.approx(0.85)


# ---------------------------------------------------------------------------
# VeraDocument.search — invalid mode
# ---------------------------------------------------------------------------

class TestVeraDocumentSearchValidation:
    def test_invalid_mode_raises_value_error(self, tmp_path):
        from test_convert_search import make_pdf
        from vera_ingest import convert

        pdf = tmp_path / "test.pdf"
        vera = tmp_path / "test.vera"
        make_pdf(pdf)
        convert(str(pdf), str(vera), model="hashing")

        doc = VeraDocument.open(str(vera))
        try:
            with pytest.raises(ValueError, match="mode must be"):
                doc.search(text="query", mode="fuzzy")
        finally:
            doc.close()


# ---------------------------------------------------------------------------
# convert() — error paths
# ---------------------------------------------------------------------------

class TestConvertErrors:
    def test_missing_input_raises_file_not_found(self, tmp_path):
        from vera_ingest.convert import convert as vera_convert

        with pytest.raises(FileNotFoundError):
            vera_convert(str(tmp_path / "missing.pdf"), str(tmp_path / "out.vera"))

    def test_unsupported_parser_raises_value_error(self, tmp_path):
        from test_convert_search import make_pdf
        from vera_ingest.convert import convert as vera_convert

        pdf = tmp_path / "test.pdf"
        make_pdf(pdf)
        with pytest.raises(ValueError, match="parser"):
            vera_convert(str(pdf), str(tmp_path / "out.vera"), parser="tika")


# ---------------------------------------------------------------------------
# str_to_bool (CLI helper)
# ---------------------------------------------------------------------------

class TestStrToBool:
    @pytest.mark.parametrize("value", ["true", "True", "TRUE", "1", "yes", "YES", "y", "on"])
    def test_truthy_values(self, value):
        assert str_to_bool(value) is True

    @pytest.mark.parametrize("value", ["false", "False", "0", "no", "n", "off", "", "random"])
    def test_falsy_values(self, value):
        assert str_to_bool(value) is False
