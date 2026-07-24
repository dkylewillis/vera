# VERA Collection Indexes

VERA keeps one portable `.vera` archive per source document. A collection index
is a disposable acceleration artifact for searching many archives as one
library; it is never the source of truth for text, citations, figures, or the
original document.

## Local index layout

`vera index build <root> --recursive` creates:

```text
<root>/
  .vera-index/
    current.json
    generations/
      generation-<id>/
        index.sqlite3
        vectors-<model-hash>-<dimension>.npy
  ... nested .vera files ...
```

SQLite stores:

- persisted discovery settings and index version
- root-relative file paths, fingerprints, and source metadata
- chunk-to-file references
- a unified FTS5 keyword index
- vector-group manifests

The NumPy files store normalized, contiguous float32 matrices grouped by
embedding model and dimension. Semantic queries run as one batched matrix
operation per model group. Results from mixed models are rank-fused, then the
winning chunk IDs are resolved against their source `.vera` files.

## Lifecycle and fallback

- `vera index build` creates a new generation in a temporary sibling directory,
  validates it, moves it under `generations/`, then atomically replaces the
  small `current.json` pointer. Existing readers can keep the previous
  generation open during publication, including on Windows. Old generations
  are retained because another process may still have one open; a future
  explicit garbage-collection command can remove generations known to be idle.
- `vera index update` rebuilds with the saved recursive and exclusion settings
  and reports added, changed, moved, and removed archives.
- `vera index status` compares the manifest with the current library and checks
  file content hashes, the SQLite database, and vector matrix shapes.
- `vera search <root>` uses a fresh index automatically. A missing or stale
  index falls back to direct corpus search using the saved discovery settings.
  Automatic searches use a fast size/mtime freshness check; `index status`
  performs the full hash verification.

Invalid archives are recorded as skipped entries so they are visible in build
reports without making an otherwise valid index permanently stale.

## Performance baseline

The deterministic benchmark in `benchmarks/benchmark_corpus.py` generated 100
archives with 100 chunks each (10,000 chunks total). On the development Windows
machine, three hybrid searches produced:

- direct fan-out median: 0.195 seconds
- local index median: 0.009 seconds
- index build: 1.071 seconds
- expected-file hit rate: 100% for both paths
- traced Python peak: 2.0 MB fan-out and 0.3 MB indexed
- index size: 21.2 MB for a 36.5 MB synthetic library

This synthetic result is hardware-specific, but it demonstrates that contiguous
local search removes most per-file SQLite and vector-deserialization overhead.
Run the benchmark with proposal-like document and chunk counts before choosing a
remote backend.

## Optional external backends

External adapters remain outside the first implementation. Introduce one only
when measurement demonstrates at least one of these requirements:

- the exact local matrix search misses the application's latency target
- vector matrices no longer fit comfortably on the serving machine
- multiple processes or hosts must update and query one shared index
- replication, tenant isolation, remote filtering, or service-level backups are
  required

A future backend contract should be additive and small:

```python
class CollectionSearchBackend(Protocol):
    def build(self, root: str, files: list[str], config: dict) -> dict: ...
    def update(self, root: str) -> dict: ...
    def status(self, root: str) -> dict: ...
    def search(self, query: str, mode: str, top_k: int) -> list[IndexHit]: ...
    def close(self) -> None: ...
```

Candidate adapters belong in an optional `vera-index` package:

- `sqlite-vec` for local ANN search when its packaging and Windows extension
  behavior are acceptable
- FAISS or HNSW for a larger local in-process index
- Qdrant for shared, concurrent, remotely operated collections

Every adapter must return root-relative `.vera` paths and chunk IDs. For
Qdrant, those values and the embedding model/dimension belong in each point's
payload. The adapter may duplicate vectors and filter metadata, but complete
source text and citation geometry continue to come from `.vera` archives.

