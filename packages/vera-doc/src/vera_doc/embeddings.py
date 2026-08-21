from __future__ import annotations

import hashlib
import logging
import os
import re
import sys
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from .embedder_descriptors import (
    EmbedderCapabilities,
    EmbedderDescriptor,
    EmbedderPreflightResult,
    EmbeddingModelInfo,
    fields_from_dataclass,
    generic_embedder_descriptor,
)
from .embedder_options import EmbedderOptions

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
_HASHING_NAME_RE = re.compile(r"^vera-hashing-(\d+)$")
SENTENCE_TRANSFORMERS_HOME_ENV = "VERA_SENTENCE_TRANSFORMERS_HOME"
BUNDLED_MINILM_MODEL_ID = "all-MiniLM-L6-v2"
BUNDLED_SENTENCE_TRANSFORMERS_DIRNAME = "sentence_transformers_models"
_ENTRY_POINT_GROUP = "vera.embedders"
_DESCRIPTOR_ENTRY_POINT_GROUP = "vera.embedder_descriptors"
_MODELS_ENTRY_POINT_GROUP = "vera.embedder_models"
_REGISTRY_LOCK = threading.RLock()
_LOAD_LOCKS_GUARD = threading.Lock()
_LOAD_LOCKS: dict[tuple[Any, ...], threading.Lock] = {}
_PROVIDERS: dict[str, Callable[..., EmbeddingFunction]] = {}
_DESCRIPTOR_FACTORIES: dict[str, Callable[[], EmbedderDescriptor]] = {}
_MODEL_LISTERS: dict[str, Callable[[], Sequence[EmbeddingModelInfo]]] = {}
_ENTRY_POINTS_LOADED = False
_INSTANCE_CACHE: dict[tuple[Any, ...], EmbeddingFunction] = {}
_ENTRY_POINT_LOAD_ERRORS: list[dict[str, str]] = []


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
            "description": (
                "Output vector length. Encoded into model_name as "
                "vera-hashing-<N> so search resolves the same size."
            ),
            "minimum": 8,
            "maximum": 4096,
            "step": 8,
            "scope": "always",
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
                "Leave blank to use CPU. "
                "Convert-time only — search may use the default device."
            ),
            "allow_empty": True,
            "placeholder": "cpu",
            "scope": "convert",
        },
    )
    batch_size: int = field(
        default=32,
        metadata={
            "label": "Batch size",
            "description": (
                "Texts encoded per Sentence Transformers batch. "
                "Convert-time only — search may use the default batch size."
            ),
            "minimum": 1,
            "maximum": 2048,
            "step": 1,
            "scope": "convert",
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


def looks_like_sentence_transformers_model(path: Path) -> bool:
    """True when ``path`` looks like a Sentence Transformers snapshot on disk."""
    if not path.is_dir():
        return False
    has_config = (path / "modules.json").is_file() or (path / "config.json").is_file()
    has_weights = (path / "model.safetensors").is_file() or (path / "pytorch_model.bin").is_file()
    return has_config and has_weights


def sentence_transformers_home() -> Path | None:
    """Return the directory that may contain vendored Sentence Transformers snapshots."""
    env = os.environ.get(SENTENCE_TRANSFORMERS_HOME_ENV, "").strip()
    if env:
        candidate = Path(env)
        if candidate.is_dir():
            return candidate
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bundled = Path(meipass) / BUNDLED_SENTENCE_TRANSFORMERS_DIRNAME
        if bundled.is_dir():
            return bundled
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        for bundled in (
            exe_dir / BUNDLED_SENTENCE_TRANSFORMERS_DIRNAME,
            exe_dir / "_internal" / BUNDLED_SENTENCE_TRANSFORMERS_DIRNAME,
        ):
            if bundled.is_dir():
                return bundled
    return None


def resolve_sentence_transformers_source(model_id: str) -> str:
    """Return a local snapshot path or a Hub id for ``SentenceTransformer()``.

    Archive identity stays the Hub-style name (``sentence-transformers/<id>``).
    This helper only chooses where weights are loaded from.
    """
    short_id = model_id
    if short_id.startswith("sentence-transformers/"):
        short_id = short_id[len("sentence-transformers/") :]
    home = sentence_transformers_home()
    if home is not None:
        direct = home / short_id
        if looks_like_sentence_transformers_model(direct):
            return str(direct)
        if home.name == short_id and looks_like_sentence_transformers_model(home):
            return str(home)
    if model_id.startswith("sentence-transformers/"):
        return model_id
    return f"sentence-transformers/{short_id}"


def bundled_minilm_available() -> bool:
    """True when the installer-vendored MiniLM snapshot is on disk."""
    source = resolve_sentence_transformers_source(BUNDLED_MINILM_MODEL_ID)
    return looks_like_sentence_transformers_model(Path(source))


class SentenceTransformerEmbedder:
    def __init__(
        self,
        model_name: str,
        *,
        source: str | None = None,
        device: str = "",
        batch_size: int = 32,
    ):
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.normalization = "l2"
        self._embed_lock = threading.Lock()
        load_path = source or model_name
        kwargs: dict[str, Any] = {"device": (device or "cpu").strip() or "cpu"}
        if Path(load_path).is_dir():
            kwargs["local_files_only"] = True
        self._model = SentenceTransformer(load_path, **kwargs)
        self._encode_kwargs = {"batch_size": int(batch_size)}
        get_dim = (
            getattr(self._model, "get_embedding_dimension", None)
            or self._model.get_sentence_embedding_dimension
        )
        dim = get_dim()
        self.dimension = int(dim or len(self.embed(["dimension probe"])[0]))

    def embed(self, texts: list[str]) -> list[np.ndarray]:
        with self._embed_lock:
            arr = self._model.encode(texts, normalize_embeddings=True, **self._encode_kwargs)
            return [np.asarray(v, dtype=np.float32) for v in arr]


def _hashing_factory(model_id: str = "vera-hashing-384", **config: Any) -> HashingEmbedder:
    raw = dict(config)
    name = (model_id or "").strip() or "vera-hashing-384"
    match = _HASHING_NAME_RE.match(name)
    if match and "dimension" not in raw:
        raw["dimension"] = int(match.group(1))
    options = HashingOptions.from_mapping(raw)
    if name in {"hashing", "vera-hashing-384"} or match is not None:
        # Keep archive identity and search resolve aligned with dimension.
        name = f"vera-hashing-{options.dimension}"
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
        source=resolve_sentence_transformers_source(model_name),
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
            supports_model_listing=True,
        ),
        fields=fields_from_dataclass(HashingOptions),
    )


def _sentence_transformers_descriptor() -> EmbedderDescriptor:
    return EmbedderDescriptor(
        provider="sentence-transformers",
        label="sentence-transformers — local neural embeddings",
        description=(
            "Sentence Transformers models via the optional ml extra (for example all-MiniLM-L6-v2). "
            "The desktop installer freezes this provider and vendors all-MiniLM-L6-v2 weights."
        ),
        default_model_id="all-MiniLM-L6-v2",
        example_specs=(
            "sentence-transformers:all-MiniLM-L6-v2",
            "sentence-transformers/all-MiniLM-L6-v2",
            "all-MiniLM-L6-v2",
        ),
        capabilities=EmbedderCapabilities(
            requires_network=not bundled_minilm_available(),
            requires_api_key=False,
            local_model=True,
            configurable_dimension=False,
            supports_model_listing=True,
        ),
        fields=fields_from_dataclass(SentenceTransformersOptions),
        notes=(
            "CLI and source-run installs need vera-doc[ml] (or sentence-transformers). "
            "The Windows installer includes all-MiniLM-L6-v2 weights, so that model "
            "does not download on first use. Other model ids may still fetch from the Hub. "
            "device and batch_size are convert-time options; search uses defaults.",
        ),
    )


def _hashing_models() -> tuple[EmbeddingModelInfo, ...]:
    return (
        EmbeddingModelInfo(
            model_id="vera-hashing-384",
            label="Hashing 384-d",
            spec="hashing:vera-hashing-384",
            description="Default deterministic offline hashing embedder.",
        ),
    )


def _sentence_transformers_models() -> tuple[EmbeddingModelInfo, ...]:
    return (
        EmbeddingModelInfo(
            model_id="all-MiniLM-L6-v2",
            label="all-MiniLM-L6-v2",
            spec="sentence-transformers:all-MiniLM-L6-v2",
            description="Compact general-purpose Sentence Transformers model.",
        ),
        EmbeddingModelInfo(
            model_id="all-MiniLM-L12-v2",
            label="all-MiniLM-L12-v2",
            spec="sentence-transformers:all-MiniLM-L12-v2",
            description="Larger MiniLM variant for slightly stronger retrieval.",
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


def register_embedder_models(
    provider: str,
    factory: Callable[[], Sequence[EmbeddingModelInfo]] | None = None,
    *,
    replace: bool = False,
) -> (
    Callable[
        [Callable[[], Sequence[EmbeddingModelInfo]]],
        Callable[[], Sequence[EmbeddingModelInfo]],
    ]
    | None
):
    """Register a model-listing callback for an embedding provider.

    Also usable as a decorator when ``factory`` is omitted — see
    :func:`register_embedder`.
    """
    if factory is None:

        def decorator(
            actual_factory: Callable[[], Sequence[EmbeddingModelInfo]],
        ) -> Callable[[], Sequence[EmbeddingModelInfo]]:
            register_embedder_models(provider, actual_factory, replace=replace)
            return actual_factory

        return decorator

    key = provider.strip().lower()
    if not key:
        raise ValueError("provider name must be non-empty")
    if ":" in key:
        raise ValueError("embedding provider name must not contain ':'")
    if not callable(factory):
        raise TypeError("embedding provider model lister must be callable")
    with _REGISTRY_LOCK:
        if key in _MODEL_LISTERS and not replace:
            raise ValueError(
                f"embedding provider model lister for {provider!r} is already registered"
            )
        _MODEL_LISTERS[key] = factory
    return None


def unregister_embedder(provider: str) -> None:
    """Remove a provider registration (primarily for tests)."""
    key = provider.strip().lower()
    with _REGISTRY_LOCK:
        _PROVIDERS.pop(key, None)
        _DESCRIPTOR_FACTORIES.pop(key, None)
        _MODEL_LISTERS.pop(key, None)
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
            raise UnknownEmbeddingModelError(_unknown_provider_message(provider))
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


def list_embedding_models(provider: str) -> list[EmbeddingModelInfo]:
    """Return model ids advertised by ``provider`` (presets and/or live listing)."""
    key = provider.strip().lower()
    if not key:
        raise ValueError("provider name must be non-empty")
    _ensure_entry_points_loaded()
    with _REGISTRY_LOCK:
        if key not in _PROVIDERS:
            raise UnknownEmbeddingModelError(_unknown_provider_message(provider))
        lister = _MODEL_LISTERS.get(key)
    if lister is None:
        descriptor = describe_embedder(key)
        default_id = descriptor.default_model_id.strip()
        if not default_id:
            return []
        return [
            EmbeddingModelInfo(
                model_id=default_id,
                label=default_id,
                spec=f"{key}:{default_id}",
            )
        ]
    models = list(lister())
    for item in models:
        if not isinstance(item, EmbeddingModelInfo):
            raise TypeError(
                f"Embedding model lister for {provider!r} must return EmbeddingModelInfo values."
            )
    return models


def preflight_embedder(model: str = "hashing") -> EmbedderPreflightResult:
    """Check whether ``model`` can be resolved without instantiating heavy runtimes.

    Validates the provider exists and, when the descriptor requires an API key,
    that ``capabilities.credential_env`` is set in the environment. Does not
    download models or call remote APIs.
    """
    try:
        provider, model_id = parse_model_spec(model)
    except UnknownEmbeddingModelError as exc:
        return EmbedderPreflightResult(
            ok=False,
            provider="",
            model_id="",
            detail=str(exc),
        )
    try:
        descriptor = describe_embedder(provider)
    except UnknownEmbeddingModelError as exc:
        return EmbedderPreflightResult(
            ok=False,
            provider=provider,
            model_id=model_id,
            detail=str(exc),
        )
    caps = descriptor.capabilities
    if caps.requires_api_key:
        env_name = (caps.credential_env or "").strip()
        if not env_name:
            return EmbedderPreflightResult(
                ok=False,
                provider=provider,
                model_id=model_id,
                detail=(
                    f"Provider {provider!r} requires an API key but did not "
                    "advertise capabilities.credential_env."
                ),
            )
        if not os.environ.get(env_name, "").strip():
            return EmbedderPreflightResult(
                ok=False,
                provider=provider,
                model_id=model_id,
                missing_credential_env=env_name,
                detail=f"Set the {env_name} environment variable before converting or searching.",
            )
    return EmbedderPreflightResult(ok=True, provider=provider, model_id=model_id)


def _register_builtins() -> None:
    with _REGISTRY_LOCK:
        _PROVIDERS.setdefault("hashing", _hashing_factory)
        _PROVIDERS.setdefault("sentence-transformers", _sentence_transformers_factory)
        _DESCRIPTOR_FACTORIES.setdefault("hashing", _hashing_descriptor)
        _DESCRIPTOR_FACTORIES.setdefault("sentence-transformers", _sentence_transformers_descriptor)
        _MODEL_LISTERS.setdefault("hashing", _hashing_models)
        _MODEL_LISTERS.setdefault("sentence-transformers", _sentence_transformers_models)


def _load_entry_point_group(group: str) -> list[Any]:
    return list(entry_points(group=group))


def _safe_load_entry_point(entry: Any, provider: str, *, kind: str) -> Any | None:
    """Load an entry point, logging a warning instead of hiding import failures."""
    try:
        return entry.load()
    except Exception as exc:  # noqa: BLE001 - one broken plugin must not hide others
        logger.warning("Failed to load %s plugin %r: %r", kind, provider, exc)
        _ENTRY_POINT_LOAD_ERRORS.append(
            {
                "provider": provider,
                "kind": kind,
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        return None


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
            factory = _safe_load_entry_point(entry, name, kind="embedding provider")
            if callable(factory):
                _PROVIDERS[name] = factory
        for entry in _load_entry_point_group(_DESCRIPTOR_ENTRY_POINT_GROUP):
            name = entry.name.strip().lower()
            if not name or name in _DESCRIPTOR_FACTORIES:
                continue
            factory = _safe_load_entry_point(entry, name, kind="embedding provider descriptor")
            if callable(factory):
                _DESCRIPTOR_FACTORIES[name] = factory
        for entry in _load_entry_point_group(_MODELS_ENTRY_POINT_GROUP):
            name = entry.name.strip().lower()
            if not name or name in _MODEL_LISTERS:
                continue
            factory = _safe_load_entry_point(entry, name, kind="embedding model lister")
            if callable(factory):
                _MODEL_LISTERS[name] = factory
        _ENTRY_POINTS_LOADED = True


def list_embedder_load_errors() -> list[dict[str, str]]:
    """Return plugin entry points that failed to load during the last registry scan.

    Failed plugins are recorded once and are not retried until
    :func:`reset_embedding_registry` runs.
    """
    _ensure_entry_points_loaded()
    with _REGISTRY_LOCK:
        return [dict(item) for item in _ENTRY_POINT_LOAD_ERRORS]


def reset_embedding_registry(*, builtins: bool = True) -> None:
    """Reset provider registry state (primarily for tests)."""
    global _ENTRY_POINTS_LOADED
    with _REGISTRY_LOCK:
        _PROVIDERS.clear()
        _DESCRIPTOR_FACTORIES.clear()
        _MODEL_LISTERS.clear()
        _INSTANCE_CACHE.clear()
        _ENTRY_POINT_LOAD_ERRORS.clear()
        _ENTRY_POINTS_LOADED = False
        if builtins:
            _register_builtins()


def parse_model_spec(model: str | None) -> tuple[str, str]:
    """Parse a model spec into ``(provider, model_id)``.

    Accepted forms:

    - ``provider:model-id`` (preferred)
    - Legacy aliases: ``hashing``, ``vera-hashing-384``, ``vera-hashing-<N>``,
      ``all-MiniLM-L6-v2``, and ``sentence-transformers/<id>``
    """
    normalized = (model or "hashing").strip()
    if not normalized:
        normalized = "hashing"

    if normalized == "hashing":
        return "hashing", "vera-hashing-384"
    if _HASHING_NAME_RE.match(normalized):
        return "hashing", normalized
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


def _unknown_provider_message(provider: str, *, model: str | None = None) -> str:
    available = ", ".join(sorted(_PROVIDERS)) or "(none)"
    if model is None:
        message = f"Unknown embedding provider {provider!r}. Registered providers: {available}."
    else:
        message = (
            f"Unknown embedding provider {provider!r} for model {model!r}. "
            f"Registered providers: {available}."
        )
    if _ENTRY_POINT_LOAD_ERRORS:
        details = "; ".join(
            f"{item['provider']} ({item['kind']}): {item['error']}"
            for item in _ENTRY_POINT_LOAD_ERRORS
        )
        message += f" Plugin load errors: {details}."
    else:
        message += (
            " Install a plugin that registers under the 'vera.embedders' "
            "entry-point group, or call register_embedder()."
        )
    return message


def _load_lock_for(key: tuple[Any, ...]) -> threading.Lock:
    with _LOAD_LOCKS_GUARD:
        lock = _LOAD_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _LOAD_LOCKS[key] = lock
        return lock


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
            raise UnknownEmbeddingModelError(_unknown_provider_message(provider, model=model))
    with _load_lock_for(key):
        with _REGISTRY_LOCK:
            cached = _INSTANCE_CACHE.get(key)
            if cached is not None:
                return cached
        embedder = factory(model_id, **resolved)
        with _REGISTRY_LOCK:
            cached = _INSTANCE_CACHE.get(key)
            if cached is not None:
                return cached
            _INSTANCE_CACHE[key] = embedder
            return embedder


_register_builtins()
