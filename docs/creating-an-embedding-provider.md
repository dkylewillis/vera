# Creating an embedding provider plugin

An embedding provider turns text into vectors for `.vera` archives. Built-in
providers (`hashing`, `sentence-transformers`) and third-party plugins share
the same contract — nothing in `vera-doc`, `vera-cli`, or `vera-app`
special-cases a hosted OpenAI or Voyage package. Write your own to add a new
API, a local runtime, or an experimental embedder.

This guide mirrors [Creating an ingest pipeline plugin](creating-an-ingest-pipeline.md):
a plain factory, one Options dataclass whose field `metadata` drives both
validation and GUI/CLI descriptors, and entry points for discovery.

## The contract

A provider factory is any callable matching this shape:

```python
def factory(model_id: str, **config) -> EmbeddingFunction:
    ...
```

The returned object must satisfy the structural `EmbeddingFunction` protocol:

- `model_name: str` — stored in archive metadata; prefer the full
  `provider:model-id` spec so later searches resolve the same provider
- `dimension: int` — vector length
- `embed(texts: list[str]) -> np.ndarray | list[np.ndarray]`
- optional `normalization` — `"l2"`, `"none"`, or omit (`"unknown"`)

There is no base class to inherit from for the embedder itself. For
configuration, subclass `EmbedderOptions` so `from_mapping` and descriptors
stay in sync.

## Minimal example

```text
vera-openai-embeddings/
  pyproject.toml
  src/vera_openai_embeddings/
    __init__.py
    options.py
    provider.py
```

`provider.py`:

```python
from __future__ import annotations

import os

import numpy as np
from openai import OpenAI

from .options import OpenAIOptions


class OpenAIEmbedder:
    normalization = "l2"

    def __init__(self, model_id: str, *, api_key: str, batch_size: int):
        self.model_name = f"openai:{model_id}"
        self._client = OpenAI(api_key=api_key or os.environ["OPENAI_API_KEY"])
        self._model = model_id
        self._batch_size = batch_size
        self.dimension = len(self.embed(["dimension probe"])[0])

    def embed(self, texts: list[str]) -> list[np.ndarray]:
        vectors = []
        for start in range(0, len(texts), self._batch_size):
            response = self._client.embeddings.create(
                model=self._model,
                input=texts[start : start + self._batch_size],
            )
            vectors.extend(item.embedding for item in response.data)
        normalized = []
        for vector in vectors:
            array = np.asarray(vector, dtype=np.float32)
            norm = np.linalg.norm(array)
            normalized.append(array / norm if norm else array)
        return normalized


def create_embedder(model_id: str, **config):
    options = OpenAIOptions.from_mapping(config)
    return OpenAIEmbedder(
        model_id,
        api_key=options.api_key,
        batch_size=options.batch_size,
    )
```

`options.py` has two jobs: validate a raw options dict into a typed config
(`from_mapping`), and describe that same config for CLI/GUI discovery
(`describe_provider`). Doing both from *one* dataclass is what
`dataclasses.field(metadata=...)` buys you:

```python
from __future__ import annotations

from dataclasses import dataclass, field

from vera import (
    EmbedderCapabilities,
    EmbedderDescriptor,
    EmbedderOptions,
)
from vera.core.embedder_descriptors import fields_from_dataclass


@dataclass(frozen=True)
class OpenAIOptions(EmbedderOptions):
    api_key: str = field(
        default="",
        metadata={
            "label": "API key",
            "description": "Optional override; otherwise uses OPENAI_API_KEY.",
            "allow_empty": True,
        },
    )
    batch_size: int = field(
        default=128,
        metadata={
            "label": "Batch size",
            "description": "Texts embedded per OpenAI request.",
            "minimum": 1,
            "maximum": 2048,
        },
    )


def describe_provider() -> EmbedderDescriptor:
    return EmbedderDescriptor(
        provider="openai",
        label="openai — hosted embeddings",
        description="OpenAI embeddings API (text-embedding-3-* and similar).",
        default_model_id="text-embedding-3-small",
        example_specs=(
            "openai:text-embedding-3-small",
            "openai:text-embedding-3-large",
        ),
        capabilities=EmbedderCapabilities(
            requires_network=True,
            requires_api_key=True,
            local_model=False,
            configurable_dimension=False,
        ),
        fields=fields_from_dataclass(OpenAIOptions),
    )
```

`__init__.py` exposes the entry-point factories:

```python
from .options import describe_provider
from .provider import create_embedder

__all__ = ["create_descriptor", "create_embedder", "describe_provider"]


def create_descriptor():
    return describe_provider()
```

## Entry points

```toml
[project.entry-points."vera.embedders"]
openai = "vera_openai_embeddings:create_embedder"

[project.entry-points."vera.embedder_descriptors"]
openai = "vera_openai_embeddings:create_descriptor"
```

After `pip install`, resolve and convert:

```bash
set OPENAI_API_KEY=...
vera convert manual.pdf --model openai:text-embedding-3-small \
  --embedder-option batch_size=64
```

```python
from vera import describe_embedder, get_embedder, register_embedder
from vera_ingest import convert

embedder = get_embedder(
    "openai:text-embedding-3-large",
    embedder_options={"batch_size": 64},
)
convert("manual.pdf", "manual.vera", embedding_function=embedder)

# Local experiments can skip packaging:
@register_embedder("myexperiment")
def create_embedder(model_id: str, **config):
    ...
```

## Descriptors without packaging

`describe_embedder("hashing")` and `list_embedding_provider_descriptors()`
power Convert UI discovery (`describe_embedding_providers` in the sidecar),
the same way ingest pipelines use `describe_ingest_pipelines`. A plugin that
omits the descriptor entry point still works for embedding; clients fall back
to a generic descriptor with no schema-driven fields.

## When *not* to inherit `EmbedderOptions`

`EmbedderOptions.from_mapping` only knows how to validate four field shapes:
a `bool`, an `int` (positive if `metadata["minimum"]` is a positive number,
otherwise non-negative), a `str` restricted to `metadata["choices"]` (unless
`allow_custom` is set), or free-text `str` (`allow_empty` permits blanks).
Override `from_mapping` when you need type conversion beyond those shapes,
cross-field checks, or normalizing values. Use
`vera.core.option_parsing` helpers directly in that override.

## Reference implementations

- Built-in hashing and Sentence Transformers providers in
  `packages/vera-doc/src/vera/core/embeddings.py` — Options + descriptors live
  beside the factories.
- This guide's OpenAI sketch — hosted API with `api_key` / `batch_size`.

See also [Convert documents](conversion.md#embedding-models) and the
[vera-doc package overview](packages/vera-doc.md).
