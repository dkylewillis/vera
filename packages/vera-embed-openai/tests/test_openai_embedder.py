"""Unit tests for the official OpenAI embeddings plugin."""

from __future__ import annotations

import io
import json
from unittest.mock import patch

import numpy as np
import pytest

from vera_doc import (
    clear_embedder_cache,
    describe_embedder,
    get_embedder,
    list_embedding_models,
    preflight_embedder,
)
from vera_embed_openai import (
    CREDENTIAL_ENV,
    DEFAULT_MODEL_ID,
    MAX_INPUT_TOKENS,
    OpenAIEmbedder,
    OpenAIEmbedderError,
    OpenAIOptions,
    create_embedder,
    embeddings_url,
    ensure_registered,
    estimate_tokens,
    iter_embed_batches,
)


def _response(vectors: list[list[float]], *, indexes: list[int] | None = None):
    payload = {
        "data": [
            {"index": (indexes[i] if indexes else i), "embedding": vector}
            for i, vector in enumerate(vectors)
        ]
    }
    raw = json.dumps(payload).encode("utf-8")

    class _Handle:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self) -> bytes:
            return raw

    return _Handle()


@pytest.fixture
def openai_key(monkeypatch):
    monkeypatch.setenv(CREDENTIAL_ENV, "sk-test")
    return "sk-test"


def test_estimate_tokens_is_conservative():
    assert estimate_tokens("") == 1
    assert estimate_tokens("abcd") == 2
    assert estimate_tokens("a" * 30) == 10


def test_iter_embed_batches_splits_on_item_cap_and_token_budget():
    texts = ["aa", "bb", "cc", "dd"]
    batches = list(iter_embed_batches(texts, batch_size=2, max_request_tokens=1000))
    assert batches == [["aa", "bb"], ["cc", "dd"]]

    # Each "aaaaaa" is 2 tokens with the heuristic; budget 3 forces size 1.
    longish = ["aaaaaa", "aaaaaa", "aaaaaa"]
    token_batches = list(iter_embed_batches(longish, batch_size=10, max_request_tokens=3))
    assert token_batches == [["aaaaaa"], ["aaaaaa"], ["aaaaaa"]]


def test_iter_embed_batches_rejects_oversized_chunk():
    huge = "a" * (MAX_INPUT_TOKENS * 3 + 3)
    with pytest.raises(OpenAIEmbedderError, match="chunk 0"):
        list(iter_embed_batches([huge], batch_size=8))


def test_embeddings_url_joins_v1_and_embeddings():
    assert embeddings_url("https://api.openai.com/v1") == "https://api.openai.com/v1/embeddings"
    assert embeddings_url("https://api.openai.com") == "https://api.openai.com/v1/embeddings"
    assert (
        embeddings_url("https://example.test/v1/embeddings")
        == "https://example.test/v1/embeddings"
    )


def test_constructor_does_not_touch_the_network(openai_key):
    calls: list[object] = []

    def boom(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("constructor must not call urlopen")

    with patch("vera_embed_openai.provider.urllib.request.urlopen", boom):
        embedder = create_embedder("text-embedding-3-small")
    assert embedder.model_name == "openai:text-embedding-3-small"
    assert embedder.dimension == 1536
    assert embedder.normalization == "l2"
    assert calls == []


def test_known_model_dimensions_need_no_probe(openai_key):
    small = OpenAIEmbedder(
        "text-embedding-3-small",
        api_key=openai_key,
        base_url="https://api.openai.com/v1",
        batch_size=8,
        timeout=5,
    )
    large = OpenAIEmbedder(
        "text-embedding-3-large",
        api_key=openai_key,
        base_url="https://api.openai.com/v1",
        batch_size=8,
        timeout=5,
    )
    ada = OpenAIEmbedder(
        "text-embedding-ada-002",
        api_key=openai_key,
        base_url="https://api.openai.com/v1",
        batch_size=8,
        timeout=5,
    )
    assert small.dimension == 1536
    assert large.dimension == 3072
    assert ada.dimension == 1536


def test_embed_normalizes_and_preserves_order(openai_key):
    embedder = create_embedder("text-embedding-3-small", batch_size=8)
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        body = json.loads(request.data.decode("utf-8"))
        captured["payload"] = body
        auth = request.headers.get("Authorization") or request.get_header("Authorization")
        captured["authorization"] = auth
        # Unnormalized, reversed indexes — client must L2-normalize and reorder.
        return _response(
            [[0.0, 3.0], [4.0, 0.0]],
            indexes=[1, 0],
        )

    with patch("vera_embed_openai.provider.urllib.request.urlopen", fake_urlopen):
        vectors = embedder.embed(["one", "two"])

    assert captured["url"] == "https://api.openai.com/v1/embeddings"
    assert captured["payload"] == {"model": "text-embedding-3-small", "input": ["one", "two"]}
    assert str(captured["authorization"]).endswith("sk-test")
    assert pytest.approx(float(np.linalg.norm(vectors[0])), abs=1e-5) == 1.0
    assert pytest.approx(float(np.linalg.norm(vectors[1])), abs=1e-5) == 1.0
    # After reorder, index 0 is [4,0] -> [1,0]; index 1 is [0,3] -> [0,1].
    assert pytest.approx(float(vectors[0][0]), abs=1e-5) == 1.0
    assert pytest.approx(float(vectors[1][1]), abs=1e-5) == 1.0


def test_embed_splits_http_requests_on_batch_size(openai_key):
    embedder = create_embedder("text-embedding-3-small", batch_size=2)
    payloads: list[list[str]] = []

    def fake_urlopen(request, timeout=None):
        body = json.loads(request.data.decode("utf-8"))
        payloads.append(list(body["input"]))
        unit = [[1.0, 0.0] for _ in body["input"]]
        return _response(unit)

    with patch("vera_embed_openai.provider.urllib.request.urlopen", fake_urlopen):
        vectors = embedder.embed(["a", "b", "c"])
    assert payloads == [["a", "b"], ["c"]]
    assert len(vectors) == 3


def test_retries_on_429_then_succeeds(openai_key, monkeypatch):
    embedder = create_embedder("text-embedding-3-small")
    attempts = {"n": 0}

    def fake_urlopen(request, timeout=None):
        attempts["n"] += 1
        if attempts["n"] == 1:
            import vera_embed_openai.provider as provider_mod

            raise provider_mod.urllib.error.HTTPError(
                request.full_url,
                429,
                "rate limited",
                hdrs={"Retry-After": "0"},
                fp=io.BytesIO(b'{"error":"slow down"}'),
            )
        return _response([[1.0, 0.0]])

    monkeypatch.setattr("vera_embed_openai.provider.time.sleep", lambda _seconds: None)
    with patch("vera_embed_openai.provider.urllib.request.urlopen", fake_urlopen):
        vectors = embedder.embed(["hello"])
    assert attempts["n"] == 2
    assert vectors[0].shape == (2,)


def test_http_error_includes_status_and_body(openai_key):
    embedder = create_embedder("text-embedding-3-small")

    def fake_urlopen(request, timeout=None):
        import vera_embed_openai.provider as provider_mod

        raise provider_mod.urllib.error.HTTPError(
            request.full_url,
            400,
            "bad request",
            hdrs={},
            fp=io.BytesIO(b'{"error":{"message":"max tokens"}}'),
        )

    with patch("vera_embed_openai.provider.urllib.request.urlopen", fake_urlopen):
        with pytest.raises(OpenAIEmbedderError, match="HTTP 400") as exc:
            embedder.embed(["hello"])
    assert "max tokens" in str(exc.value)


def test_missing_api_key_fails_in_factory(monkeypatch):
    monkeypatch.delenv(CREDENTIAL_ENV, raising=False)
    with pytest.raises(OpenAIEmbedderError, match="OPENAI_API_KEY"):
        create_embedder("text-embedding-3-small")


def test_options_validate_bounds():
    options = OpenAIOptions.from_mapping({"batch_size": 16, "timeout": 30})
    assert options.batch_size == 16
    assert options.timeout == 30
    with pytest.raises(ValueError, match="batch_size"):
        OpenAIOptions.from_mapping({"batch_size": 0})
    with pytest.raises(ValueError, match="timeout"):
        OpenAIOptions.from_mapping({"timeout": 0})


def test_ensure_registered_descriptor_and_preflight(monkeypatch, openai_key):
    ensure_registered()
    try:
        descriptor = describe_embedder("openai")
        assert descriptor.provider == "openai"
        assert descriptor.capabilities.credential_env == CREDENTIAL_ENV
        assert descriptor.capabilities.requires_api_key is True
        models = list_embedding_models("openai")
        assert any(item.model_id == DEFAULT_MODEL_ID for item in models)
        assert preflight_embedder("openai:text-embedding-3-small").ok is True
        monkeypatch.delenv(CREDENTIAL_ENV, raising=False)
        failed = preflight_embedder("openai:text-embedding-3-large")
        assert failed.ok is False
        assert failed.missing_credential_env == CREDENTIAL_ENV
        monkeypatch.setenv(CREDENTIAL_ENV, openai_key)
        embedder = get_embedder("openai:text-embedding-3-small")
        assert embedder.model_name == "openai:text-embedding-3-small"
        assert embedder.dimension == 1536
    finally:
        clear_embedder_cache()


def test_unknown_model_probes_dimension_lazily(openai_key):
    calls = {"n": 0}

    def fake_urlopen(request, timeout=None):
        calls["n"] += 1
        return _response([[0.6, 0.8]])

    embedder = create_embedder("text-embedding-custom")
    assert calls["n"] == 0
    with patch("vera_embed_openai.provider.urllib.request.urlopen", fake_urlopen):
        assert embedder.dimension == 2
    assert calls["n"] == 1
