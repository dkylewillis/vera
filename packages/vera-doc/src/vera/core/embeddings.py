from __future__ import annotations

import hashlib
import re
import threading
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import Any, Callable, Iterable, Protocol

import numpy as np

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
_ENTRY_POINT_GROUP = "vera.embedders"
_REGISTRY_LOCK = threading.RLock()
_PROVIDERS: dict[str, Callable[..., EmbeddingFunction]] = {}
_ENTRY_POINTS_LOADED = False
_INSTANCE_CACHE: dict[tuple[Any, ...], EmbeddingFunction] = {}


def serialize_vector(vector: Iterable[float]) -> bytes:
    return np.asarray(list(vector), dtype="<f4").tobytes()


def deserialize_vector(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype="<f4")


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


class EmbeddingFunction(Protocol):
    """Structural protocol for embedders used when writing and querying archives.

    Implementations may also expose a ``normalization`` attribute
    (``"l2"``, ``"none"``, or ``"unknown"``). Embedders without it are
    recorded as ``"unknown"``.

    Attributes:
        model_name: Identifier stored in archive metadata.
        dimension: Vector length expected by the database.
    """

    model_name: str
    dimension: int

    def embed(self, texts: list[str]) -> np.ndarray | list[np.ndarray]:
        """Embed a batch of texts."""
        ...


# Back-compat alias used by internal call sites.
Embedder = EmbeddingFunction


class UnknownEmbeddingModelError(ValueError):
    """Raised when a model spec cannot be resolved to a registered provider."""


@dataclass
class HashingEmbedder:
    """Deterministic offline lexical embedder for portable tests and no-network use."""

    dimension: int = 384
    model_name: str = "vera-hashing-384"
    normalization: str = "l2"

    def embed(self, texts: list[str]) -> list[np.ndarray]:
        vectors = []
        for text in texts:
            vector = np.zeros(self.dimension, dtype=np.float32)
            for token in _TOKEN_RE.findall(text.lower()):
                digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
                bucket = int.from_bytes(digest[:4], "little") % self.dimension
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                # Sublinear token frequency dampening while preserving repeated topical terms.
                vector[bucket] += sign
            norm = np.linalg.norm(vector)
            if norm:
                vector /= norm
            vectors.append(vector.astype(np.float32))
        return vectors


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str, **config: Any):
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.normalization = "l2"
        encode_kwargs = {}
        if "device" in config and config["device"] is not None:
            self._model = SentenceTransformer(model_name, device=config["device"])
        else:
            self._model = SentenceTransformer(model_name)
        if "batch_size" in config and config["batch_size"] is not None:
            encode_kwargs["batch_size"] = int(config["batch_size"])
        self._encode_kwargs = encode_kwargs
        get_dim = getattr(self._model, "get_embedding_dimension", None) or self._model.get_sentence_embedding_dimension
        dim = get_dim()
        self.dimension = int(dim or len(self.embed(["dimension probe"])[0]))

    def embed(self, texts: list[str]) -> list[np.ndarray]:
        arr = self._model.encode(texts, normalize_embeddings=True, **self._encode_kwargs)
        return [np.asarray(v, dtype=np.float32) for v in arr]


def _hashing_factory(model_id: str = "vera-hashing-384", **config: Any) -> HashingEmbedder:
    dimension = int(config.get("dimension", 384))
    name = model_id.strip() or "vera-hashing-384"
    if name in {"hashing", "vera-hashing-384"}:
        name = "vera-hashing-384"
    return HashingEmbedder(dimension=dimension, model_name=name)


def _sentence_transformers_factory(model_id: str, **config: Any) -> SentenceTransformerEmbedder:
    model_id = (model_id or "").strip()
    if not model_id:
        raise UnknownEmbeddingModelError(
            "sentence-transformers provider requires a model id "
            "(e.g. 'sentence-transformers:all-MiniLM-L6-v2')"
        )
    if model_id.startswith("sentence-transformers/"):
        model_name = model_id
    else:
        model_name = f"sentence-transformers/{model_id}"
    return SentenceTransformerEmbedder(model_name, **config)


def register_embedder(
    provider: str,
    factory: Callable[..., EmbeddingFunction],
    *,
    replace: bool = False,
) -> None:
    """Register an embedding provider factory under ``provider``.

    Factories are called as ``factory(model_id, **config)`` and must return an
    object satisfying :class:`EmbeddingFunction`.
    """
    key = provider.strip().lower()
    if not key:
        raise ValueError("provider name must be non-empty")
    with _REGISTRY_LOCK:
        if key in _PROVIDERS and not replace:
            raise ValueError(f"embedding provider {provider!r} is already registered")
        _PROVIDERS[key] = factory
        _INSTANCE_CACHE.clear()


def unregister_embedder(provider: str) -> None:
    """Remove a provider registration (primarily for tests)."""
    key = provider.strip().lower()
    with _REGISTRY_LOCK:
        _PROVIDERS.pop(key, None)
        _INSTANCE_CACHE.clear()


def clear_embedder_cache() -> None:
    """Drop cached embedder instances."""
    with _REGISTRY_LOCK:
        _INSTANCE_CACHE.clear()


def list_embedding_providers() -> list[str]:
    """Return sorted registered provider names, loading entry points first."""
    _ensure_entry_points_loaded()
    with _REGISTRY_LOCK:
        return sorted(_PROVIDERS)


def _register_builtins() -> None:
    with _REGISTRY_LOCK:
        _PROVIDERS.setdefault("hashing", _hashing_factory)
        _PROVIDERS.setdefault("sentence-transformers", _sentence_transformers_factory)


def _ensure_entry_points_loaded() -> None:
    global _ENTRY_POINTS_LOADED
    with _REGISTRY_LOCK:
        if _ENTRY_POINTS_LOADED:
            return
        _register_builtins()
        try:
            selected = entry_points(group=_ENTRY_POINT_GROUP)
        except TypeError:  # pragma: no cover - Python <3.10 compatibility path
            selected = entry_points().get(_ENTRY_POINT_GROUP, [])  # type: ignore[index]
        for entry in selected:
            name = entry.name.strip().lower()
            if not name or name in _PROVIDERS:
                continue
            try:
                factory = entry.load()
            except Exception:
                continue
            _PROVIDERS[name] = factory
        _ENTRY_POINTS_LOADED = True


def reset_embedding_registry(*, builtins: bool = True) -> None:
    """Reset provider registry state (primarily for tests)."""
    global _ENTRY_POINTS_LOADED
    with _REGISTRY_LOCK:
        _PROVIDERS.clear()
        _INSTANCE_CACHE.clear()
        _ENTRY_POINTS_LOADED = False
        if builtins:
            _register_builtins()


def parse_model_spec(model: str | None) -> tuple[str, str]:
    """Parse a model spec into ``(provider, model_id)``.

    Accepted forms:

    - ``provider:model-id`` (preferred)
    - Legacy aliases: ``hashing``, ``vera-hashing-384``, ``all-MiniLM-L6-v2``,
      and ``sentence-transformers/<id>``
    """
    normalized = (model or "hashing").strip()
    if not normalized:
        normalized = "hashing"

    if normalized in {"hashing", "vera-hashing-384"}:
        return "hashing", "vera-hashing-384"
    if normalized == "all-MiniLM-L6-v2":
        return "sentence-transformers", "all-MiniLM-L6-v2"
    if normalized.startswith("sentence-transformers/"):
        return "sentence-transformers", normalized[len("sentence-transformers/") :]

    if ":" in normalized:
        provider, model_id = normalized.split(":", 1)
        provider = provider.strip()
        model_id = model_id.strip()
        if provider:
            return provider.lower(), model_id

    raise UnknownEmbeddingModelError(
        f"Unknown embedding model {normalized!r}. "
        "Use 'provider:model-id' (for example 'hashing:vera-hashing-384' or "
        "'sentence-transformers:all-MiniLM-L6-v2'), a built-in legacy alias, "
        "or install a plugin that registers under the 'vera.embedders' entry-point group."
    )


def _cache_key(provider: str, model_id: str, config: dict[str, Any]) -> tuple[Any, ...]:
    items = tuple(sorted((str(key), repr(value)) for key, value in config.items()))
    return (provider, model_id, items)


def get_embedder(model: str = "hashing", **config: Any) -> EmbeddingFunction:
    """Resolve ``model`` to a registered embedder instance.

    Args:
        model: Model spec string (``provider:model-id`` or a legacy alias).
        **config: Provider-specific keyword arguments forwarded to the factory.

    Raises:
        UnknownEmbeddingModelError: When the provider is not registered.
    """
    provider, model_id = parse_model_spec(model)
    _ensure_entry_points_loaded()
    key = _cache_key(provider, model_id, config)
    with _REGISTRY_LOCK:
        cached = _INSTANCE_CACHE.get(key)
        if cached is not None:
            return cached
        factory = _PROVIDERS.get(provider)
        if factory is None:
            available = ", ".join(sorted(_PROVIDERS)) or "(none)"
            raise UnknownEmbeddingModelError(
                f"Unknown embedding provider {provider!r} for model {model!r}. "
                f"Registered providers: {available}. "
                "Install a plugin that registers under the 'vera.embedders' "
                "entry-point group, or call register_embedder()."
            )
        embedder = factory(model_id, **config)
        _INSTANCE_CACHE[key] = embedder
        return embedder


_register_builtins()
