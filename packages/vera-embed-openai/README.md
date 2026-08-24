# vera-embed-openai

Official OpenAI embeddings plugin for VERA. Registers the `openai` provider
under the `vera.embedders` entry-point group.

`vera-cli` and `vera-app` depend on this package so hosted OpenAI conversion
works out of the box. The client uses stdlib `urllib` — there is no `openai`
SDK dependency.

## Install

```bash
python -m pip install "vera-embed-openai>=0.3.0"
```

From a repository checkout with uv, the workspace installs it by default
(via `vera-cli` / `vera-app`):

```bash
uv sync
```

## Usage

```bash
set OPENAI_API_KEY=...
vera convert "manual.pdf" --model openai:text-embedding-3-small
```

```python
import os

from vera_ingest import convert

os.environ["OPENAI_API_KEY"] = "..."
convert("manual.pdf", "manual.vera", model="openai:text-embedding-3-small")
```

Keep the API key in `OPENAI_API_KEY`. Optional `OPENAI_BASE_URL` (default
`https://api.openai.com/v1`) points at Azure, OpenRouter, or a local
OpenAI-compatible server. Archives still record `openai:<model-id>`, so two
endpoints that embed different models under the same id are indistinguishable
at search time.

## Notes

- Known dimensions (no network in the constructor): `text-embedding-3-small`
  1536, `text-embedding-3-large` 3072, `text-embedding-ada-002` 1536.
  Unrecognized model ids probe once on first use.
- Convert-time options: `batch_size` (1–2048) and `timeout` seconds.
  Search resolves `get_embedder(stored_model_name)` with defaults.
- Semantic search of a hosted archive needs the same provider and credentials
  on the searching machine. Keyword search still works without a key.
- Desktop Convert Cancel does not interrupt an in-flight embeddings HTTP
  batch; conversion checks cancellation after `embed()` returns.

See the [vera-embed-openai documentation](https://dkylewillis.github.io/vera/packages/vera-embed-openai/)
and [conversion guide](https://github.com/dkylewillis/vera/blob/main/docs/conversion.md).
