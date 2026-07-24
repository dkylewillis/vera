# Examples and recipes

These recipes use the `vera` console script. Substitute
`python -m vera_cli` if the console script is not on `PATH`.

## Convert and search one document

```bash
vera convert "ordinance.pdf" "ordinance.vera" --model hashing
vera inspect "ordinance.vera"
vera validate "ordinance.vera"
vera search "ordinance.vera" "minimum parking required for restaurant" --mode hybrid --top-k 5
```

## Get JSON with surrounding context

```bash
vera search "ordinance.vera" \
  "restaurant parking requirements" \
  --mode hybrid \
  --top-k 5 \
  --context-chunks 1 \
  --json
```

PowerShell equivalent:

```powershell
vera search "ordinance.vera" `
  "restaurant parking requirements" `
  --mode hybrid `
  --top-k 5 `
  --context-chunks 1 `
  --json
```

## Find an exact identifier

```bash
vera search "ordinance.vera" "EL-A zoning district" --mode keyword --top-k 10 --json
```

Confirm that `EL-A` appears literally in the result text. Keyword fallback can
remove punctuation and broaden short identifiers.

## Find a figure or chart

```bash
vera search "manual.vera" "pipe sizing chart" --top-k 5 --figures --json
```

Use the returned caption and page as the citation. The CLI returns figure
metadata, not image bytes.

## Get source highlight regions

```bash
vera search "manual.vera" "detention requirements" --top-k 5 --regions --json
```

The returned top-left-origin bounding boxes can be scaled onto a page viewer.

## Convert and index a nested library

```bash
vera convert "./proposals" --recursive --json
vera index build "./proposals" --recursive --exclude "archive/**" --json
vera search "./proposals" "termination clause" --top-k 10 --json
```

After adding or replacing documents:

```bash
vera index status "./proposals" --json
vera index update "./proposals" --json
```

`index status` exits 1 when the index is stale or missing while still printing
a JSON report.

## Compare several documents

```bash
vera search "./policies" "employee eligibility requirements" --top-k 10 --json
```

Each corpus result includes `file`. Group findings and citations by source
archive rather than merging conflicting provisions.

## Export the embedded source

```bash
vera export "ordinance.vera" "./exports" --json
```

## Evaluate retrieval changes

Create `queries.json`:

```json
[
  {
    "query": "restaurant parking",
    "expected_pages": [42, 43],
    "expected_terms": ["parking"],
    "note": "Parking schedule"
  }
]
```

Run all search modes:

```bash
vera eval "ordinance.vera" "queries.json" --mode all --top-k 5 --json
```

The command exits 1 if any expected answer is missed. See
[Evaluate retrieval quality](evaluation.md) for hit rules and metric guidance.

## Search from Python

```python
from vera import VeraDocument

doc = VeraDocument.open("ordinance.vera")
try:
    for result in doc.search("restaurant parking", mode="hybrid", top_k=5):
        print(result.score, result.page_start, result.heading_path)
        print(result.text)
finally:
    doc.close()
```

## Search a library from Python

```python
from vera import VeraCorpus

with VeraCorpus.open("./proposals", recursive=True) as corpus:
    for result in corpus.search("termination clause", top_k=10):
        print(result.file, result.page_start, result.text[:100])
```

See the [getting-started tutorial](getting-started.md), [search guide](searching.md),
and [Python API](python-api.md) for details.
