# SDX — Semantic Document eXchange

SDX is a portable semantic document exchange format that stores a document, parsed pages, chunks, embeddings, keyword indexes, and citation metadata in one SQLite `.sdx` file.

Tagline: **Convert once. Search anywhere.**

## MVP

```bash
sdx convert input.pdf output.sdx
sdx inspect output.sdx
sdx validate output.sdx
sdx search output.sdx "stream buffer requirements" --mode hybrid
```

Python:

```python
from sdx import convert, SDXDocument
convert("input.pdf", "output.sdx")
doc = SDXDocument.open("output.sdx")
print(doc.search("parking requirements", mode="hybrid"))
```

The MVP uses SQLite + FTS5 and brute-force cosine vector search. Hybrid search min-max normalizes both score sets and blends them equally. It supports PyMuPDF parsing and a deterministic local hashing embedder by default, with optional sentence-transformers support via `--model sentence-transformers/all-MiniLM-L6-v2`.

Conversion performs structured block-level parsing: headings are detected from font size/weight and produce hierarchical heading paths (`Chapter 110 > Article 5 > Parking`), chunks map back to their source blocks via `chunk_blocks`, and embedded images are extracted into the `assets` table. Figures co-located with a search result are available via the Python API:

```python
doc = SDXDocument.open("output.sdx")
result = doc.search("parking requirements", top_k=1)[0]
figures = doc.figures_for(result, include_data=True)  # images on the result's pages
```


## Testing

Run the automated suite:

```bash
uv run --extra dev pytest -q
```

Validate a generated SDX file:

```bash
uv run python -m sdx.cli validate output.sdx
```

Measure retrieval quality against an expected-answer query set:

```bash
uv run python -m sdx.cli eval output.sdx queries.json --mode all --top-k 5
```

Query files are JSON (or YAML with pyyaml installed) lists of cases:

```json
[
  {"query": "restaurant parking", "expected_page": 42, "expected_terms": ["parking"]}
]
```

The command reports hit rate and MRR per search mode, and exits non-zero if any query misses — handy for CI regression checks. See [examples/docling-queries.json](examples/docling-queries.json) for a working example.

## SDX Workbench

For easy manual testing, install the optional Streamlit extra and launch the workbench:

```bash
uv run --extra workbench python -m sdx.cli workbench
```

The workbench lets you upload a PDF, convert it to `.sdx`, inspect metadata, run validation, browse chunks, and compare semantic/keyword/hybrid search results.
