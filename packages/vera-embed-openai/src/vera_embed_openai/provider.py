"""Stdlib HTTP OpenAI embeddings client.

Batch splitting, retries, and URL construction stay in this module. The
``EmbeddingFunction`` contract is ``embed(texts)``, so convert and search
never see request boundaries.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator, Sequence
from typing import Any

import numpy as np

from .options import (
    BASE_URL_ENV,
    CREDENTIAL_ENV,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL_ID,
    MODEL_DIMENSIONS,
    PROVIDER,
    OpenAIOptions,
)

# OpenAI embeddings caps (re-check against current docs if these start failing).
# Per-input limit for text-embedding-3-* and ada-002.
MAX_INPUT_TOKENS = 8192
# Published per-request cap is ~300k tokens; stay under it to absorb the
# character heuristic's estimation error.
MAX_REQUEST_TOKENS = 250_000
MAX_BATCH_ITEMS = 2048
MAX_RETRIES = 4
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_SURROGATE_RE = re.compile(r"[\ud800-\udfff]")


class OpenAIEmbedderError(RuntimeError):
    """Raised when the OpenAI embeddings API rejects or cannot complete a request."""


def estimate_tokens(text: str) -> int:
    """Conservative character heuristic (~3 chars/token). Over-estimates on purpose."""
    if not text:
        return 1
    return max(1, (len(text) + 2) // 3)


def iter_embed_batches(
    texts: Sequence[str],
    *,
    batch_size: int,
    max_request_tokens: int = MAX_REQUEST_TOKENS,
    max_input_tokens: int = MAX_INPUT_TOKENS,
) -> Iterator[list[str]]:
    """Yield text batches that fit both the item cap and the token budget.

    A single text over ``max_input_tokens`` raises rather than truncating.
    """
    max_items = max(1, min(int(batch_size), MAX_BATCH_ITEMS))
    budget = max(1, int(max_request_tokens))
    batch: list[str] = []
    batch_tokens = 0
    for index, text in enumerate(texts):
        value = text if isinstance(text, str) else ("" if text is None else str(text))
        tokens = estimate_tokens(value)
        if tokens > max_input_tokens:
            raise OpenAIEmbedderError(
                f"chunk {index} is ~{tokens} tokens, over the {max_input_tokens} "
                "per-input OpenAI embeddings limit; lower the pipeline chunk_size"
            )
        if batch and (len(batch) >= max_items or batch_tokens + tokens > budget):
            yield batch
            batch = []
            batch_tokens = 0
        batch.append(value)
        batch_tokens += tokens
    if batch:
        yield batch


def embeddings_url(base_url: str) -> str:
    """Join ``base_url`` with ``/embeddings``, inserting ``/v1`` when missing."""
    root = (base_url or DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL
    root = root.rstrip("/")
    if root.endswith("/embeddings"):
        return root
    if not root.endswith("/v1") and "/v1/" not in root + "/":
        root = f"{root}/v1"
    return f"{root}/embeddings"


def _sanitize_unicode(value: Any) -> Any:
    if isinstance(value, str):
        return _SURROGATE_RE.sub("\ufffd", value)
    if isinstance(value, list):
        return [_sanitize_unicode(item) for item in value]
    if isinstance(value, dict):
        return {
            _sanitize_unicode(key) if isinstance(key, str) else key: _sanitize_unicode(item)
            for key, item in value.items()
        }
    return value


def _l2_normalize(vector: np.ndarray) -> np.ndarray:
    array = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(array))
    if norm:
        array = array / norm
    return array.astype(np.float32)


def _retry_delay_seconds(headers: Any, attempt: int) -> float:
    raw = ""
    if headers is not None:
        raw = str(headers.get("Retry-After") or headers.get("retry-after") or "")
    if raw:
        try:
            return min(60.0, max(0.5, float(raw.strip())))
        except ValueError:
            pass
    return min(32.0, 0.5 * (2**attempt))


def _error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - error path must not hide the status
        body = ""
    snippet = " ".join(body.split())
    if len(snippet) > 500:
        snippet = snippet[:497] + "..."
    return snippet


def _post_embeddings(
    *,
    url: str,
    api_key: str,
    model: str,
    inputs: list[str],
    timeout: float,
) -> list[np.ndarray]:
    payload = json.dumps(
        _sanitize_unicode({"model": model, "input": inputs}),
        ensure_ascii=False,
    ).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = json.loads(response.read().decode("utf-8"))
            return _vectors_from_payload(raw, expected=len(inputs))
        except urllib.error.HTTPError as exc:
            detail = _error_detail(exc)
            if exc.code in _RETRY_STATUS and attempt + 1 < MAX_RETRIES:
                time.sleep(_retry_delay_seconds(exc.headers, attempt))
                last_error = OpenAIEmbedderError(
                    f"OpenAI embeddings HTTP {exc.code}: {detail or exc.reason}"
                )
                continue
            raise OpenAIEmbedderError(
                f"OpenAI embeddings HTTP {exc.code}: {detail or exc.reason}"
            ) from exc
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            last_error = OpenAIEmbedderError(f"Unable to reach OpenAI embeddings API: {reason}")
            if attempt + 1 < MAX_RETRIES:
                time.sleep(_retry_delay_seconds(None, attempt))
                continue
            raise last_error from exc
        except (json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
            raise OpenAIEmbedderError(
                f"OpenAI embeddings returned an invalid payload: {exc}"
            ) from exc
    raise last_error or OpenAIEmbedderError("OpenAI embeddings request failed")


def _vectors_from_payload(payload: Any, *, expected: int) -> list[np.ndarray]:
    if not isinstance(payload, dict):
        raise OpenAIEmbedderError("OpenAI embeddings response is not a JSON object")
    rows = payload.get("data")
    if not isinstance(rows, list) or len(rows) != expected:
        raise OpenAIEmbedderError(
            f"OpenAI embeddings returned {0 if not isinstance(rows, list) else len(rows)} "
            f"vectors; expected {expected}"
        )
    indexed: list[tuple[int, np.ndarray]] = []
    for position, row in enumerate(rows):
        if not isinstance(row, dict):
            raise OpenAIEmbedderError("OpenAI embeddings data entry is not an object")
        embedding = row.get("embedding")
        if not isinstance(embedding, list) or not embedding:
            raise OpenAIEmbedderError("OpenAI embeddings data entry is missing embedding")
        index = row.get("index", position)
        try:
            order = int(index)
        except (TypeError, ValueError) as exc:
            raise OpenAIEmbedderError("OpenAI embeddings data entry has an invalid index") from exc
        indexed.append((order, _l2_normalize(np.asarray(embedding, dtype=np.float32))))
    indexed.sort(key=lambda item: item[0])
    return [vector for _index, vector in indexed]


class OpenAIEmbedder:
    """Hosted OpenAI embeddings. Constructor does not touch the network."""

    normalization = "l2"

    def __init__(
        self,
        model_id: str,
        *,
        api_key: str,
        base_url: str,
        batch_size: int,
        timeout: int,
    ) -> None:
        model = (model_id or "").strip() or DEFAULT_MODEL_ID
        self.model_name = f"{PROVIDER}:{model}"
        self._model = model
        self._api_key = api_key
        self._url = embeddings_url(base_url)
        self._batch_size = max(1, min(int(batch_size), MAX_BATCH_ITEMS))
        self._timeout = float(timeout)
        self._lock = threading.Lock()
        self._dimension = MODEL_DIMENSIONS.get(model)

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            self._dimension = int(len(self._embed_one_batch(["ping"])[0]))
        return self._dimension

    def embed(self, texts: list[str]) -> list[np.ndarray]:
        if not texts:
            return []
        vectors: list[np.ndarray] = []
        for batch in iter_embed_batches(texts, batch_size=self._batch_size):
            vectors.extend(self._embed_one_batch(batch))
        if self._dimension is None and vectors:
            self._dimension = int(vectors[0].shape[0])
        return vectors

    def _embed_one_batch(self, batch: list[str]) -> list[np.ndarray]:
        with self._lock:
            return _post_embeddings(
                url=self._url,
                api_key=self._api_key,
                model=self._model,
                inputs=batch,
                timeout=self._timeout,
            )


def _require_api_key() -> str:
    api_key = os.environ.get(CREDENTIAL_ENV, "").strip()
    if not api_key:
        raise OpenAIEmbedderError(
            f"Set the {CREDENTIAL_ENV} environment variable before converting or searching "
            "with an OpenAI embedding model. In the desktop app, save it under "
            "File > Settings → Embeddings."
        )
    return api_key


def create_embedder(model_id: str, **config: Any) -> OpenAIEmbedder:
    """Entry-point factory for ``vera.embedders`` provider ``openai``."""
    options = OpenAIOptions.from_mapping(config)
    model = (model_id or "").strip() or DEFAULT_MODEL_ID
    base_url = os.environ.get(BASE_URL_ENV, "").strip() or DEFAULT_BASE_URL
    return OpenAIEmbedder(
        model,
        api_key=_require_api_key(),
        base_url=base_url,
        batch_size=options.batch_size,
        timeout=options.timeout,
    )
