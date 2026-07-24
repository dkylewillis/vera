# Search documents

VERA supports semantic, keyword, and hybrid search over the content already
stored in an archive. Search is local and does not require a retrieval server.

## Basic search

```bash
vera search "manual.vera" "stormwater detention requirements"
```

The default mode is `hybrid` and the default result limit is 10:

```bash
vera search "manual.vera" "stormwater detention requirements" --mode hybrid --top-k 10
```

Use `--json` for scripts and agents:

```bash
vera search "manual.vera" "stormwater detention requirements" --top-k 5 --json
```

## Choose a search mode

### Hybrid

```bash
vera search "manual.vera" "when must runoff be detained?" --mode hybrid
```

Hybrid combines normalized semantic and keyword rankings. Use it for most
questions, especially when both concepts and document terminology matter.

### Keyword

```bash
vera search "manual.vera" "\"Section 4.2\"" --mode keyword
```

Keyword search uses SQLite FTS5. Use it for exact phrases, section numbers,
identifiers, table labels, and known terminology.

If an FTS query cannot be used directly or has no hits, VERA can fall back to a
broader token-prefix query. Punctuation may be removed during that fallback.
For short or hyphenated identifiers, confirm that the literal identifier
appears in the returned text.

### Semantic

```bash
vera search "manual.vera" "how does the site reduce peak flow?" --mode semantic
```

Semantic search compares the query embedding with stored chunk embeddings. Use
it when the wording is likely to differ from the document.

## Interpret results

Every result contains:

- `chunk_id`
- `score`
- `text`
- `page_start` and `page_end`
- `heading_path`
- `source_filename`
- `document_id`

Scores rank results within a search. They are not probabilities or confidence
values, and scores from different queries or modes should not be compared as
though they share one scale.

Treat the text and its location as evidence. A citation should include the
source filename, page or page range, and heading when available:

```text
(manual.pdf, p. 117, Chapter 4 > Detention Design)
```

## Include neighboring chunks

A result may begin after a definition or end before an exception. Include
neighboring chunks:

```bash
vera search "manual.vera" "detention requirements" --context-chunks 1 --json
```

Each result gains `before_chunks` and `after_chunks`. These chunks are ordered
in document sequence and carry their own citation fields.

## Find figures and page regions

Add figure metadata:

```bash
vera search "manual.vera" "pipe sizing chart" --figures --json
```

Add source block bounding boxes:

```bash
vera search "manual.vera" "detention requirements" --regions --json
```

See [Figures and highlight regions](figures-and-regions.md) for the coordinate
contract and limitations.

## Improve a weak search

If results are too broad:

- add the governing action: `requirements`, `definition`, `exceptions`;
- add a section, district, facility type, or threshold;
- switch to keyword mode for exact language.

If results are sparse:

- remove one constraint;
- use a likely synonym;
- search the parent concept;
- switch to semantic mode;
- increase `--top-k`.

Split compound questions into separate searches. For comprehensive research,
use several targeted queries and synthesize only claims supported by the
retrieved text.

## Empty and failed searches

An empty successful search returns `results: []` and exits 0. It means no
candidate was returned for that query and mode; it does not prove the concept
is absent from the document.

Missing paths, unreadable archives, unavailable embedding dependencies, and
directories with no archives generally exit nonzero and write an error to
stderr. Check the process exit code before parsing JSON.

## Search a library

Pass a directory instead of a file to search multiple archives as one corpus:

```bash
vera search "./library" "termination clause" --json
```

See [Document libraries](document-libraries.md) for recursive discovery,
exclusions, collection indexes, stale-index fallback, and mixed embedding
models.
