# Creating an embedding provider plugin

An embedding provider turns text into vectors for `.vera` archives. Built-in
providers (`hashing`, `sentence-transformers`) and third-party plugins share
the same contract — nothing in `vera-doc`, `vera-cli`, or `vera-app`
special-cases a hosted OpenAI or Voyage package. Write your own to add a new
API, a local runtime, or an experimental embedder.

Registry and descriptor APIs (`register_embedder`, descriptor/model listing
helpers) are experimental and may change before 1.0. Hosted providers
(OpenAI, Voyage, Ollama) are examples you can implement yourself; they are
not bundled with VERA.

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
  `provider:model-id` spec (or an identity-encoding name such as
  `vera-hashing-128`) so later searches resolve the same provider
- `dimension: int` — vector length
- `embed(texts: list[str]) -> np.ndarray | list[np.ndarray]`
- optional `normalization` — `"l2"`, `"none"`, or omit (`"unknown"`)

There is no base class to inherit from for the embedder itself. For
configuration, subclass `EmbedderOptions` so `from_mapping` and descriptors
stay in sync.

### Convert-time vs search-time

Archives store `model_name`, dimension, and normalization — not your
`--embedder-option` bag. At search time VERA typically calls
`get_embedder(stored_model_name)` with **defaults**.

- Mark throughput/hardware settings with `metadata={"scope": "convert"}`
  (device, batch size, timeouts). Search may ignore them and use defaults.
- Mark identity-affecting settings with `metadata={"scope": "always"}` and
  encode them in `model_name` (hashing does this as `vera-hashing-<N>`).
- **Do not put API keys in Options.** Advertise
  `capabilities.credential_env` (for example `OPENAI_API_KEY`) and read the
  environment inside the factory. The desktop app will store secrets
  separately; Options fields must stay non-secret.

Use `preflight_embedder("openai:text-embedding-3-small")` to check that a
required credential env var is present without loading model weights. Desktop
Convert calls this automatically; CLI `vera convert` and `vera_ingest.convert()`
do not. Official hosted embedding packages (OpenAI, Voyage, Ollama) and their
Settings UI are 0.3.1 follow-ups. Options fields must stay non-secret.

If a `vera.embedders` entry point fails to import, the provider is absent from
`list_embedding_providers()`. Inspect `vera_doc.embeddings.list_embedder_load_errors()`
(not exported from `vera_doc`) and restart after fixing the plugin. Failed
entries are not retried until `reset_embedding_registry()` runs.

Install the package in the same environment as VERA (`python -m pip install`
or `python -m pip install -e <clone>`), then restart the app. Bundled
`hashing` wins on duplicate names. Sentence Transformers is the workspace
`ml` extra for CLI and source-run installs. The Windows installer freezes
`sentence_transformers` and vendors `all-MiniLM-L6-v2` weights.

## Minimal example (DIY hosted provider)

The OpenAI sketch below is an example you can implement yourself. OpenAI,
Voyage, and Ollama are not bundled with VERA.

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

    def __init__(self, model_id: str, *, batch_size: int):
        self.model_name = f"openai:{model_id}"
        self._client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
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
    return OpenAIEmbedder(model_id, batch_size=options.batch_size)
```

`options.py` validates convert-time knobs and describes them for CLI/GUI
discovery. Credentials stay out of the dataclass:

```python
from __future__ import annotations

from dataclasses import dataclass, field

from vera_doc import (
    EmbedderCapabilities,
    EmbedderDescriptor,
    EmbedderOptions,
    EmbeddingModelInfo,
)
from vera_doc.embedder_descriptors import fields_from_dataclass


@dataclass(frozen=True)
class OpenAIOptions(EmbedderOptions):
    batch_size: int = field(
        default=128,
        metadata={
            "label": "Batch size",
            "description": "Texts embedded per OpenAI request (convert-time).",
            "minimum": 1,
            "maximum": 2048,
            "scope": "convert",
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
            credential_env="OPENAI_API_KEY",
            local_model=False,
            configurable_dimension=False,
            supports_model_listing=True,
        ),
        fields=fields_from_dataclass(OpenAIOptions),
    )


def list_models() -> tuple[EmbeddingModelInfo, ...]:
    return (
        EmbeddingModelInfo(
            model_id="text-embedding-3-small",
            label="text-embedding-3-small",
            spec="openai:text-embedding-3-small",
        ),
        EmbeddingModelInfo(
            model_id="text-embedding-3-large",
            label="text-embedding-3-large",
            spec="openai:text-embedding-3-large",
        ),
    )
```

`__init__.py` exposes the entry-point factories:

```python
from .options import describe_provider, list_models
from .provider import create_embedder

__all__ = [
    "create_descriptor",
    "create_embedder",
    "describe_provider",
    "list_models",
]


def create_descriptor():
    return describe_provider()
```

## Entry points

```toml
[project.entry-points."vera.embedders"]
openai = "vera_openai_embeddings:create_embedder"

[project.entry-points."vera.embedder_descriptors"]
openai = "vera_openai_embeddings:create_descriptor"

[project.entry-points."vera.embedder_models"]
openai = "vera_openai_embeddings:list_models"
```

After `pip install`, resolve and convert:

```bash
set OPENAI_API_KEY=...
vera convert manual.pdf --model openai:text-embedding-3-small \
  --embedder-option batch_size=64
```

```python
from vera_doc import (
    describe_embedder,
    get_embedder,
    list_embedding_models,
    preflight_embedder,
    register_embedder,
)
from vera_ingest import convert

assert preflight_embedder("openai:text-embedding-3-small").ok
embedder = get_embedder(
    "openai:text-embedding-3-large",
    embedder_options={"batch_size": 64},
)
convert("manual.pdf", "manual.vera", embedding_function=embedder)

# Later searches only need the stored model_name (+ env credentials):
# get_embedder("openai:text-embedding-3-large")

# Local experiments can skip packaging:
@register_embedder("myexperiment")
def create_embedder(model_id: str, **config):
    ...
```

## Descriptors and model listing

`describe_embedder("hashing")` and `list_embedding_provider_descriptors()`
power Convert UI discovery (`describe_embedding_providers` in the sidecar).
`list_embedding_models(provider)` / sidecar `list_embedding_models` advertise
preset or live model ids when `supports_model_listing` is true. A plugin that
omits descriptor or model entry points still works for embedding; clients fall
back to a generic descriptor and the provider's `default_model_id`.

## When *not* to inherit `EmbedderOptions`

`EmbedderOptions.from_mapping` only knows how to validate four field shapes:
a `bool`, an `int` (bounded by `metadata["minimum"]` / `metadata["maximum"]`
when those are set; otherwise non-negative), a `str` restricted to
`metadata["choices"]` (unless `allow_custom` is set), or free-text `str`
(`allow_empty` permits blanks).
Override `from_mapping` when you need type conversion beyond those shapes,
cross-field checks, or normalizing values. Use
`vera_doc.option_parsing` helpers directly in that override.

## Reference implementations

- Built-in hashing and Sentence Transformers providers in
  `packages/vera-doc/src/vera_doc/embeddings.py` — Options + descriptors +
  model lists live beside the factories.
- This guide's OpenAI sketch — hosted API with env credentials and
  convert-time `batch_size`.

See also [Convert documents](conversion.md#embedding-models) and the
[vera-doc package overview](packages/vera-doc.md).
