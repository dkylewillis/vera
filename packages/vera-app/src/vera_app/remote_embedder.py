"""EmbeddingFunction proxy that embeds through the plugin host."""

from __future__ import annotations

import base64
from collections import OrderedDict
from collections.abc import Mapping
from typing import Any

import numpy as np

from vera_app.plugin_host import PluginHost, current_request_cancel
from vera_app.runtime import PLUGIN_HOST_EMBED_TIMEOUT_S
from vera_doc.embeddings import deserialize_vector

_QUERY_CACHE_SIZE = 32


class RemoteEmbedder:
    """Satisfy :class:`~vera_doc.embeddings.EmbeddingFunction` over JSON-lines RPC."""

    def __init__(
        self,
        host: PluginHost,
        model: str,
        *,
        embedder_options: Mapping[str, Any] | None = None,
    ):
        self._host = host
        self._model = model
        self._embedder_options = dict(embedder_options or {})
        info = host.request(
            {
                "action": "embedder_info",
                "model": model,
                "embedder_options": self._embedder_options,
            },
            timeout=PLUGIN_HOST_EMBED_TIMEOUT_S,
            cancel=current_request_cancel(),
        )
        self.model_name = str(info.get("model_name") or model)
        self.dimension = int(info.get("dimension") or 0)
        self.normalization = str(info.get("normalization") or "unknown")
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()

    def embed(self, texts: list[str]) -> list[np.ndarray]:
        if len(texts) == 1:
            cached = self._cache.get(texts[0])
            if cached is not None:
                self._cache.move_to_end(texts[0])
                return [cached.copy()]
        result = self._host.request(
            {
                "action": "embed",
                "model": self._model,
                "texts": texts,
                "embedder_options": self._embedder_options,
            },
            timeout=PLUGIN_HOST_EMBED_TIMEOUT_S,
            cancel=current_request_cancel(),
        )
        raw_vectors = result.get("vectors")
        if not isinstance(raw_vectors, list) or len(raw_vectors) != len(texts):
            raise RuntimeError("Plugin host embed returned an unexpected vector payload")
        vectors = [
            np.asarray(deserialize_vector(base64.b64decode(item)), dtype=np.float32)
            for item in raw_vectors
        ]
        if len(texts) == 1:
            self._cache[texts[0]] = vectors[0].copy()
            while len(self._cache) > _QUERY_CACHE_SIZE:
                self._cache.popitem(last=False)
        return vectors
