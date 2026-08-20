# Document libraries

Pass a directory to `vera search` to search multiple `.vera` files as one
corpus. Results are ranked together and attributed to their source archive.

## Search a flat directory

```bash
vera search "./library" "termination clause" --top-k 10
```

Only `.vera` files directly inside the directory are discovered by default.

JSON results add:

- `file` on each result, identifying its `.vera` archive;
- a top-level `index` object describing whether a collection index was used;
- a top-level `skipped_files` array containing the absolute path, category, and
  validation reason for each rejected archive.

Keep citations separated by archive when comparing sources.

Malformed archives do not abort folder search or inspection. Direct fallback
search validates each discovered archive and searches the valid subset.
`VeraCorpus.inspect()` similarly reports `discovered_file_count`, the valid
`file_count`, `skipped`, and `skipped_files`.

## Search nested directories

Without a collection index, enable recursive discovery explicitly:

```bash
vera search "./library" "termination clause" --recursive --json
```

Exclude paths or names with repeatable patterns:

```bash
vera search "./library" "termination clause" \
  --recursive \
  --exclude "archive/**" \
  --exclude "*.draft.vera" \
  --json
```

Patterns are matched against forward-slash relative paths and individual path
components. Directory symlinks and archive symlinks are not followed.

## Build a collection index

Direct corpus search opens and searches individual archives. For a larger or
frequently searched library, build a local index:

```bash
vera index build "./library" --recursive --json
```

The index stores its discovery settings, file manifest, unified keyword index,
chunk references, and per-model vector matrices under:

```text
library/.vera-index/
```

The index is a rebuildable local acceleration artifact. It does not modify the
`.vera` files, and the archives remain independently portable. It persists
across process and app restarts. Opening a library does not rebuild its index;
only an explicit build or update writes a new generation. A successful rebuild
deletes every other generation directory under `.vera-index/generations/`.

Use the same exclusion patterns while building:

```bash
vera index build "./library" \
  --recursive \
  --exclude "archive/**" \
  --json
```

## Search an indexed library

Search the directory normally:

```bash
vera search "./library" "termination clause" --json
```

VERA automatically uses a fresh index. You do not need to repeat `--recursive`
or `--exclude`; the saved index settings control discovery.

The response reports:

```json
{
  "index": {
    "used": true,
    "exists": true,
    "fresh": true,
    "reasons": []
  }
}
```

Treat `index.used`, not merely `index.exists`, as the indication that indexed
search was active. The `index.skipped_files` array retains relative paths,
categories, and reasons recorded when the active index was built. Inspection
uses this manifest and does not reopen archives that the fresh index already
rejected.

`VeraCorpus.inspect_summary()` also reads file, page, chunk, and model metrics
from a fresh index without reopening any source archives. With a missing or
stale index it returns discovery counts and marks `summary_complete` false;
call `VeraCorpus.inspect()` when an explicit deep validation scan is required.

## Check and update freshness

```bash
vera index status "./library" --json
```

An index becomes stale when archives are added, removed, moved, replaced, or
changed, or when an index artifact is missing or incompatible. A stale or
missing status still prints JSON but exits with status 1.

Rebuild using the saved discovery settings:

```bash
vera index update "./library" --json
```

Run update after changing the library contents.

## Safe fallback

If the index is missing or stale, corpus search falls back to direct file
search. The JSON response sets `index.used` to false and lists the reason:

```json
{
  "index": {
    "used": false,
    "exists": true,
    "fresh": false,
    "reasons": ["library files were added, removed, or moved"]
  }
}
```

This preserves correctness while making the performance change visible.

`vera index status --json` also reports the active generation and timestamps,
database/vector/total storage, `indexed_chunks` versus `source_chunks`
coverage, discovery settings, skipped files, and a `model_groups` array with
dimensions and document/chunk counts. These fields power the desktop app's
Library Info view. On current builds the two chunk counters match; older
indexes may report indexed chunks as the source total until rebuilt.

## Mixed embedding models

A library may contain archives created with different embedding models.
VERA queries each model group with its recorded model and rank-fuses the
groups. The runtime must have the dependency required by every model it needs
to query. Archives created with Sentence Transformers therefore require the
`ml` extra at search time.

If an indexed semantic or hybrid search cannot load a group's model, or the
runtime model's dimension differs from the indexed dimension, VERA skips that
semantic group and reports it:

```json
{
  "skipped_semantic_model_groups": [
    {
      "model_name": "sentence-transformers/all-MiniLM-L6-v2",
      "dimension": 384,
      "error": "ImportError: No module named 'sentence_transformers'"
    }
  ]
}
```

This array is empty for keyword-only searches. Hybrid search can still return
keyword matches, but its semantic coverage is incomplete whenever the array is
non-empty.

Corpus ranking is not identical to single-document ranking. Direct semantic
search can merge raw cosine scores for archives sharing a model, while mixed
models and keyword/hybrid corpus results require rank fusion. Indexed hybrid
search also fuses ranked semantic and keyword lists. Use scores to order one
result set; do not compare score values across single-document, direct-corpus,
and indexed-corpus searches.

## Python API

Search a library directly:

```python
from vera_doc import VeraCorpus

with VeraCorpus.open("./library", recursive=True) as corpus:
    results = corpus.search("termination clause", mode="hybrid", top_k=10)
    for result in results:
        print(result.file, result.page_start, result.text[:100])
```

`VeraCorpus.open(..., allow_empty=True)` is available to applications that
need to represent an empty library during setup. The default remains strict
and raises `FileNotFoundError` when discovery finds no `.vera` archives.

The corpus opens source archives lazily and uses a bounded handle cache. See
[Python API](python-api.md) and the detailed
[collection index design](collection-index.md).
