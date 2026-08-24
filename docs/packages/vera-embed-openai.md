# vera-embed-openai

Official OpenAI embeddings plugin for VERA. It registers the `openai`
provider under the `vera.embedders` entry-point group. `vera-cli` and
`vera-app` depend on this package so hosted OpenAI conversion works out of
the box. The client uses stdlib `urllib`; there is no `openai` SDK
dependency.

`vera-doc` does not special-case OpenAI. This package is an ordinary plugin
on the same contract as a third-party embedder.

## Install

```bash
python -m pip install "vera-embed-openai>=0.3.0"
```

From a repository checkout with uv, the workspace installs it by default:

```bash
uv sync
```

## Usage

```bash
set OPENAI_API_KEY=...
vera convert "manual.pdf" --model openai:text-embedding-3-small
vera convert "manual.pdf" --model openai:text-embedding-3-large \
  --embedder-option batch_size=64
```

```python
import os
from vera_ingest import convert

os.environ["OPENAI_API_KEY"] = "..."
convert("manual.pdf", "manual.vera", model="openai:text-embedding-3-small")
```

Keep the API key in `OPENAI_API_KEY`. The desktop app stores it under
**File > Settings → Embeddings** using the same encrypted env-secret store
as other sidecar credentials. Missing `OPENAI_API_KEY` or embeddings HTTP
failures raise `OpenAIEmbedderError`; `vera convert --json` and
`vera search --json` report that as `{"ok": false, "error": "..."}` (exit 1).
Optional `OPENAI_BASE_URL` (default
`https://api.openai.com/v1`) points at Azure, OpenRouter, or a local
OpenAI-compatible server. Archives still record `openai:<model-id>`, so two
endpoints that embed different models under the same id are indistinguishable
at search time.

## Behavior

- Known dimensions (constructor does not touch the network):
  `text-embedding-3-small` 1536, `text-embedding-3-large` 3072,
  `text-embedding-ada-002` 1536. Unrecognized model ids probe once on first
  use.
- Convert-time options: `batch_size` (1–2048 texts, also split on an
  estimated token budget) and `timeout` seconds. Search resolves
  `get_embedder(stored_model_name)` with defaults.
- Responses are L2-normalized. `model_name` is the full spec
  (`openai:text-embedding-3-small`).
- A single chunk over the per-input token limit raises instead of truncating.
- HTTP 429 and 5xx responses retry with backoff, honoring `Retry-After`.

## Portability

Archives converted with this provider are **not portable for semantic or
hybrid search**. A recipient needs their own `OPENAI_API_KEY` (and a
reachable API) because search resolves `get_embedder(stored_model_name)`.
Keyword search still works without a key. Corpus search reports
`skipped_semantic_model_groups` when the query embedder cannot load.

Conversion bills per request. Desktop Convert Cancel does not interrupt an
in-flight embeddings HTTP batch; conversion checks cancellation after
`embed()` returns.

## Desktop app

The packaged sidecar freezes this plugin, copies its package metadata, and
calls `ensure_registered()` so PyInstaller builds still resolve `openai`
when dist-info is missing. Convert lists OpenAI presets beside hashing and
MiniLM. Hashing remains the default.

## See also

- [Convert documents](../conversion.md)
- [Creating an embedding provider plugin](../creating-an-embedding-provider.md)
- [vera-doc](vera-doc.md)
