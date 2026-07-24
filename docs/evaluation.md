# Evaluate retrieval quality

`vera eval` measures whether expected answers appear in the top search results.
Use it when changing embedding models, chunking, parsing, ranking, or a document
library's conversion settings.

## Create a query set

Query files are non-empty JSON lists:

```json
[
  {
    "query": "restaurant parking",
    "expected_pages": [42, 43],
    "expected_terms": ["parking", "restaurant"],
    "note": "Parking schedule"
  }
]
```

Every case requires `query` plus at least one of:

- `expected_pages`: one or more acceptable pages;
- `expected_terms`: terms that must all occur in the result text.

When both are supplied, a result must overlap an expected page and contain all
expected terms to count as a hit.

`expected_page` is also accepted as a single-page shorthand.

YAML files are supported only when PyYAML is installed:

```bash
python -m pip install pyyaml
```

## Run an evaluation

Compare every search mode:

```bash
vera eval "manual.vera" "queries.json" --mode all --top-k 5
```

Evaluate one mode:

```bash
vera eval "manual.vera" "queries.json" --mode hybrid --top-k 5 --json
```

Valid modes are `semantic`, `keyword`, `hybrid`, and `all`.

## Interpret the report

Each mode reports:

- total query count;
- hits;
- hit rate;
- mean reciprocal rank (MRR);
- per-query hit status and matching rank;
- top score and top page.

Hit rate measures whether an expected answer appeared within `top_k`. MRR also
rewards placing the first matching result near the top.

The command exits 0 only when every query hits in every requested mode. A miss
returns exit status 1 while still printing the complete report.

## Compare changes fairly

- Use the same source archive or rebuild it intentionally for both runs.
- Keep the query file and `top_k` fixed.
- Record embedding model, chunk size, overlap, parser, and VERA version.
- Include lexical, paraphrased, exact-identifier, and figure-caption queries
  that represent real use.
- Review individual misses; aggregate metrics do not explain why retrieval
  changed.

Example query sets live under [`examples/`](../examples/).

## Python API

```python
from vera.evaluate import evaluate

summary = evaluate(
    "manual.vera",
    "queries.json",
    mode="all",
    top_k=5,
)
```

Lower-level imports include `QueryCase`, `load_queries`, and
`evaluate_document`.
