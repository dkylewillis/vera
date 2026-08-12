from __future__ import annotations

import hashlib
import re
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from typing import Any, Callable, Iterable, Protocol

import numpy as np

from .embedder_descriptors import (
    EmbedderCapabilities,
    EmbedderDescriptor,
    fields_from_dataclass,
    generic_embedder_descriptor,
)
from .embedder_options import EmbedderOptions

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
_ENTRY_POINT_GROUP = "vera.embedders"
_DESCRIPTOR_ENTRY_POINT_GROUP = "vera.embedder_descriptors"
_REGISTRY_LOCK = threading.RLock()
_PROVIDERS: dict[str, Callable[..., EmbeddingFunction]] = {}
_DESCRIPTOR_FACTORIES: dict[str, Callable[[], EmbedderDescriptor]] = {}
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


@dataclass(frozen=True)
class HashingOptions(EmbedderOptions):
    """Settings for the built-in hashing embedder."""

    dimension: int = field(
        default=384,
        metadata={
            "label": "Dimension",
            "description": "Output vector length for the hashing embedder.",
            "minimum": 8,
            "maximum": 4096,
            "step": 8,
        },
    )


@dataclass(frozen=True)
class SentenceTransformersOptions(EmbedderOptions):
    """Settings for the Sentence Transformers provider."""

    device: str = field(
        default="",
        metadata={
            "label": "Device",
            "description": (
                "Optional torch device (for example cpu or cuda). "
                "Leave blank to let Sentence Transformers choose."
            ),
            "allow_empty": True,
            "placeholder": "cpu",
        },
    )
    batch_size: int = field(
        default=32,
        metadata={
            "label": "Batch size",
            "description": "Texts encoded per Sentence Transformers batch.",
            "minimum": 1,
            "maximum": 2048,
            "step": 1,
        },
    )


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
    def __init__(self, model_name: str, *, device: str = "", batch_size: int = 32):
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.normalization = "l2"
        if device:
            self._model = SentenceTransformer(model_name, device=device)
        else:
            self._model = SentenceTransformer(model_name)
        self._encode_kwargs = {"batch_size": int(batch_size)}
        get_dim = getattr(self._model, "get_embedding_dimension", None) or self._model.get_sentence_embedding_dimension
        dim = get_dim()
        self.dimension = int(dim or len(self.embed(["dimension probe"])[0]))

    def embed(self, texts: list[str]) -> list[np.ndarray]:
        arr = self._model.encode(texts, normalize_embeddings=True, **self._encode_kwargs)
        return [np.asarray(v, dtype=np.float32) for v in arr]


def _hashing_factory(model_id: str = "vera-hashing-384", **config: Any) -> HashingEmbedder:
    options = HashingOptions.from_mapping(config)
    name = (model_id or "").strip() or "vera-hashing-384"
    if name in {"hashing", "vera-hashing-384"}:
        name = "vera-hashing-384"
    return HashingEmbedder(dimension=options.dimension, model_name=name)


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
    options = SentenceTransformersOptions.from_mapping(config)
    return SentenceTransformerEmbedder(
        model_name,
        device=options.device,
        batch_size=options.batch_size,
    )


def _hashing_descriptor() -> EmbedderDescriptor:
    return EmbedderDescriptor(
        provider="hashing",
        label="hashing — deterministic offline embedder",
        description=(
            "Local lexical hashing embedder for portable tests and no-network use. "
            "Does not require model downloads or API keys."
        ),
        default_model_id="vera-hashing-384",
        example_specs=("hashing", "hashing:vera-hashing-384", "vera-hashing-384"),
        capabilities=EmbedderCapabilities(
            requires_network=False,
            requires_api_key=False,
            local_model=True,
            configurable_dimension=True,
        ),
        fields=fields_from_dataclass(HashingOptions),
    )


def _sentence_transformers_descriptor() -> EmbedderDescriptor:
    return EmbedderDescriptor(
        provider="sentence-transformers",
        label="sentence-transformers — local neural embeddings",
        description=(
            "Sentence Transformers models via the optional ml extra "
            "(for example all-MiniLM-L6-v2)."
        ),
        default_model_id="all-MiniLM-L6-v2",
        example_specs=(
            "sentence-transformers:all-MiniLM-L6-v2",
            "sentence-transformers/all-MiniLM-L6-v2",
            "all-MiniLM-L6-v2",
        ),
        capabilities=EmbedderCapabilities(
            requires_network=True,
            requires_api_key=False,
            local_model=True,
            configurable_dimension=False,
        ),
        fields=fields_from_dataclass(SentenceTransformersOptions),
        notes=(
            "Install vera-doc[ml] (or sentence-transformers) before first use. "
            "The first resolve may download model weights.",
        ),
    )


def register_embedder(
    provider: str,
    factory: Callable[..., EmbeddingFunction] | None = None,
    *,
    replace: bool = False,
) -> Callable[[Callable[..., EmbeddingFunction]], Callable[..., EmbeddingFunction]] | None:
    """Register an embedding provider factory under ``provider``.

    Factories are called as ``factory(model_id, **config)`` and must return an
    object satisfying :class:`EmbeddingFunction`.

    Called with both arguments, this registers ``factory`` immediately and
    returns ``None``. Omit ``factory`` to use it as a decorator::

        @register_embedder("myexperiment")
        def create_embedder(model_id: str, **config):
            return MyEmbedder(model_id, **config)
    """
    if factory is None:
        def decorator(
            actual_factory: Callable[..., EmbeddingFunction],
        ) -> Callable[..., EmbeddingFunction]:
            register_embedder(provider, actual_factory, replace=replace)
            return actual_factory

        return decorator

    key = provider.strip().lower()
    if not key:
        raise ValueError("provider name must be non-empty")
    if ":" in key:
        raise ValueError("embedding provider name must not contain ':'")
    if not callable(factory):
        raise TypeError("embedding provider factory must be callable")
    with _REGISTRY_LOCK:
        if key in _PROVIDERS and not replace:
            raise ValueError(f"embedding provider {provider!r} is already registered")
        _PROVIDERS[key] = factory
        _INSTANCE_CACHE.clear()
    return None


def register_embedder_descriptor(
    provider: str,
    factory: Callable[[], EmbedderDescriptor] | None = None,
    *,
    replace: bool = False,
) -> Callable[[Callable[[], EmbedderDescriptor]], Callable[[], EmbedderDescriptor]] | None:
    """Register a descriptor factory for an embedding provider.

    Also usable as a decorator when ``factory`` is omitted — see
    :func:`register_embedder`.
    """
    if factory is None:
        def decorator(
            actual_factory: Callable[[], EmbedderDescriptor],
        ) -> Callable[[], EmbedderDescriptor]:
            register_embedder_descriptor(provider, actual_factory, replace=replace)
            return actual_factory

        return decorator

    key = provider.strip().lower()
    if not key:
        raise ValueError("provider name must be non-empty")
    if ":" in key:
        raise ValueError("embedding provider name must not contain ':'")
    if not callable(factory):
        raise TypeError("embedding provider descriptor factory must be callable")
    with _REGISTRY_LOCK:
        if key in _DESCRIPTOR_FACTORIES and not replace:
            raise ValueError(
                f"embedding provider descriptor for {provider!r} is already registered"
            )
        _DESCRIPTOR_FACTORIES[key] = factory
    return None


def unregister_embedder(provider: str) -> None:
    """Remove a provider registration (primarily for tests)."""
    key = provider.strip().lower()
    with _REGISTRY_LOCK:
        _PROVIDERS.pop(key, None)
        _DESCRIPTOR_FACTORIES.pop(key, None)
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


def describe_embedder(provider: str) -> EmbedderDescriptor:
    """Return metadata for an installed provider without instantiating it."""
    key = provider.strip().lower()
    if not key:
        raise ValueError("provider name must be non-empty")
    _ensure_entry_points_loaded()
    with _REGISTRY_LOCK:
        if key not in _PROVIDERS:
            available = ", ".join(sorted(_PROVIDERS)) or "(none)"
            raise UnknownEmbeddingModelError(
                f"Unknown embedding provider {provider!r}. "
                f"Registered providers: {available}. "
                "Install a plugin that registers under the 'vera.embedders' "
                "entry-point group, or call register_embedder()."
            )
        factory = _DESCRIPTOR_FACTORIES.get(key)
        if factory is None:
            return generic_embedder_descriptor(key)
        descriptor = factory()
        if not isinstance(descriptor, EmbedderDescriptor):
            raise TypeError(
                f"Embedding provider descriptor for {provider!r} must return EmbedderDescriptor."
            )
        return descriptor


def list_embedding_provider_descriptors() -> list[EmbedderDescriptor]:
    """Return descriptors for each installed embedding provider."""
    return [describe_embedder(provider) for provider in list_embedding_providers()]


def _register_builtins() -> None:
    with _REGISTRY_LOCK:
        _PROVIDERS.setdefault("hashing", _hashing_factory)
        _PROVIDERS.setdefault("sentence-transformers", _sentence_transformers_factory)
        _DESCRIPTOR_FACTORIES.setdefault("hashing", _hashing_descriptor)
        _DESCRIPTOR_FACTORIES.setdefault(
            "sentence-transformers", _sentence_transformers_descriptor
        )


def _load_entry_point_group(group: str) -> list[Any]:
    try:
        selected = entry_points(group=group)
    except TypeError:  # pragma: no cover - Python <3.10 compatibility path
        selected = entry_points().get(group, [])  # type: ignore[index]
    return list(selected)


def _ensure_entry_points_loaded() -> None:
    global _ENTRY_POINTS_LOADED
    with _REGISTRY_LOCK:
        if _ENTRY_POINTS_LOADED:
            return
        _register_builtins()
        for entry in _load_entry_point_group(_ENTRY_POINT_GROUP):
            name = entry.name.strip().lower()
            if not name or name in _PROVIDERS:
                continue
            try:
                factory = entry.load()
            except Exception:  # noqa: BLE001, S112 - one broken plugin must not hide others
                continue
            if callable(factory):
                _PROVIDERS[name] = factory
        for entry in _load_entry_point_group(_DESCRIPTOR_ENTRY_POINT_GROUP):
            name = entry.name.strip().lower()
            if not name or name in _DESCRIPTOR_FACTORIES:
                continue
            try:
                factory = entry.load()
            except Exception:  # noqa: BLE001, S112
                continue
            if callable(factory):
                _DESCRIPTOR_FACTORIES[name] = factory
        _ENTRY_POINTS_LOADED = True


def reset_embedding_registry(*, builtins: bool = True) -> None:
    """Reset provider registry state (primarily for tests)."""
    global _ENTRY_POINTS_LOADED
    with _REGISTRY_LOCK:
        _PROVIDERS.clear()
        _DESCRIPTOR_FACTORIES.clear()
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


def _merge_embedder_config(
    embedder_options: Mapping[str, Any] | None,
    config: dict[str, Any],
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if embedder_options:
        if not isinstance(embedder_options, Mapping):
            raise TypeError("embedder_options must be a mapping of string keys")
        merged.update({str(key): value for key, value in embedder_options.items()})
    merged.update(config)
    return merged


def get_embedder(
    model: str = "hashing",
    *,
    embedder_options: Mapping[str, Any] | None = None,
    **config: Any,
) -> EmbeddingFunction:
    """Resolve ``model`` to a registered embedder instance.

    Args:
        model: Model spec string (``provider:model-id`` or a legacy alias).
        embedder_options: Provider-owned options mapping (same keys a plugin's
            ``Options`` dataclass advertises). Keyword ``config`` values win
            for the same key.
        **config: Provider-specific keyword arguments forwarded to the factory.

    Raises:
        UnknownEmbeddingModelError: When the provider is not registered.
    """
    provider, model_id = parse_model_spec(model)
    resolved = _merge_embedder_config(embedder_options, config)
    _ensure_entry_points_loaded()
    key = _cache_key(provider, model_id, resolved)
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
        embedder = factory(model_id, **resolved)
        _INSTANCE_CACHE[key] = embedder
        return embedder


_register_builtins()
