# Creating an embedding provider plugin

An embedding provider turns text into vectors for `.vera` archives. Built-in
providers (`hashing`, `sentence-transformers`) and third-party plugins share
the same contract — nothing in `vera-doc`, `vera-cli`, or `vera-app`
special-cases a hosted OpenAI or Voyage package. Write your own to add a new
API, a local runtime, or an experimental embedder.

Registry and descriptor APIs (`register_embedder`, descriptor/model listing
helpers) are experimental and may change before 1.0. The official OpenAI
plugin is [`vera-embed-openai`](packages/vera-embed-openai.md), bundled with
`vera-cli` and the desktop sidecar. Voyage and Ollama are not bundled with
VERA; they need a query-versus-document hint on `EmbeddingFunction` first.

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
  environment inside the factory. The desktop app stores those secrets under
  **File > Settings → Embeddings**; Options fields must stay non-secret.

Use `preflight_embedder("openai:text-embedding-3-small")` to check that a
required credential env var is present without loading model weights. Desktop
Convert calls this automatically; CLI `vera convert` and `vera_ingest.convert()`
do not. Options fields must stay non-secret.

**Do not call the network from `__init__`.** `VeraDocument.open(..., mode="write")`
resolves `get_embedder(stored_model_name)` only to validate dimension, and
`preflight_embedder` is deliberately network-free. A constructor that embeds a
dummy string on every write-mode open bills an API call and can fail offline.
Ship a static dimension table for known ids and probe unrecognized ids lazily
(on first `embed()` or a `dimension` property). The official OpenAI package
does both.

If a `vera.embedders` entry point fails to import, the provider is absent from
`list_embedding_providers()`. Inspect `vera_doc.embeddings.list_embedder_load_errors()`
(not exported from `vera_doc`) and restart after fixing the plugin. Failed
entries are not retried until `reset_embedding_registry()` runs.

Install the package in the same environment as VERA (`python -m pip install`
or `python -m pip install -e <clone>`), then restart the app. Bundled
`hashing` wins on duplicate names. MiniLM uses the workspace `onnx` extra
(ONNX Runtime) when a MiniLM graph is present and the `ml` extra
(Sentence Transformers) otherwise. Other Sentence Transformers
models always use the `ml` extra. The Windows installer freezes ONNX
Runtime and vendors a VERA-exported `all-MiniLM-L6-v2` graph. Archive identity
stays `sentence-transformers/all-MiniLM-L6-v2` under either runtime.

## Official OpenAI package

Use [`vera-embed-openai`](packages/vera-embed-openai.md) as the reference
implementation for a hosted API: stdlib `urllib` (no SDK), `credential_env =
"OPENAI_API_KEY"`, convert-time `batch_size` / `timeout`, token-aware request
splitting, L2 normalization, and a constructor that never touches the network.
`vera-cli` and `vera-app` depend on it; the frozen sidecar calls
`ensure_registered()`.

```bash
set OPENAI_API_KEY=...
vera convert manual.pdf --model openai:text-embedding-3-small \
  --embedder-option batch_size=64
```

Archives converted with it are **not portable for semantic or hybrid search**:
a recipient needs their own `OPENAI_API_KEY`. Keyword search still works.

## Minimal example (DIY hosted provider)

The sketch below is a third-party pattern. Copy
[`packages/vera-embed-openai`](https://github.com/dkylewillis/vera/tree/main/packages/vera-embed-openai)
when you want the official OpenAI client; use this skeleton for another API.
Voyage and Ollama are not bundled with VERA.

```text
vera-myhost-embeddings/
  pyproject.toml
  src/vera_myhost_embeddings/
    __init__.py
    options.py
    provider.py
```

`provider.py` — factory reads the env secret; the constructor does **not**
probe dimension over the network:

```python
from __future__ import annotations

import os

import numpy as np

from .options import KNOWN_DIMENSIONS, MyHostOptions


class MyHostEmbedder:
    normalization = "l2"

    def __init__(self, model_id: str, *, batch_size: int):
        self.model_name = f"myhost:{model_id}"
        self._api_key = os.environ["MYHOST_API_KEY"]
        self._model = model_id
        self._batch_size = batch_size
        self.dimension = KNOWN_DIMENSIONS[model_id]

    def embed(self, texts: list[str]) -> list[np.ndarray]:
        vectors = []
        for start in range(0, len(texts), self._batch_size):
            vectors.extend(self._embed_batch(texts[start : start + self._batch_size]))
        return vectors

    def _embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        raise NotImplementedError("POST the provider embeddings API here")


def create_embedder(model_id: str, **config):
    options = MyHostOptions.from_mapping(config)
    return MyHostEmbedder(model_id, batch_size=options.batch_size)
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

KNOWN_DIMENSIONS = {"alpha-small": 1536}


@dataclass(frozen=True)
class MyHostOptions(EmbedderOptions):
    batch_size: int = field(
        default=128,
        metadata={
            "label": "Batch size",
            "description": "Texts embedded per request (convert-time).",
            "minimum": 1,
            "maximum": 2048,
            "scope": "convert",
        },
    )


def describe_provider() -> EmbedderDescriptor:
    return EmbedderDescriptor(
        provider="myhost",
        label="myhost — hosted embeddings",
        description="Example hosted embeddings API.",
        default_model_id="alpha-small",
        example_specs=("myhost:alpha-small",),
        capabilities=EmbedderCapabilities(
            requires_network=True,
            requires_api_key=True,
            credential_env="MYHOST_API_KEY",
            local_model=False,
            configurable_dimension=False,
            supports_model_listing=True,
        ),
        fields=fields_from_dataclass(MyHostOptions),
    )


def list_models() -> tuple[EmbeddingModelInfo, ...]:
    return (
        EmbeddingModelInfo(
            model_id="alpha-small",
            label="alpha-small",
            spec="myhost:alpha-small",
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
myhost = "vera_myhost_embeddings:create_embedder"

[project.entry-points."vera.embedder_descriptors"]
myhost = "vera_myhost_embeddings:create_descriptor"

[project.entry-points."vera.embedder_models"]
myhost = "vera_myhost_embeddings:list_models"
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

Broken `vera.embedders` (or descriptor/model-lister) entry points are logged
as warnings and omitted from `list_embedding_providers()`.
`UnknownEmbeddingModelError` then includes `Plugin load errors:` with the
provider, kind, and exception so a failed import is not mistaken for an
unknown name.

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
- Official OpenAI plugin in `packages/vera-embed-openai` — stdlib HTTPS,
  static dimensions, token-aware batching, no network in the constructor.

See also [Convert documents](conversion.md#embedding-models) and the
[vera-doc package overview](packages/vera-doc.md).
