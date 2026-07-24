# VERA retrieval workflows

Use these workflows after loading the main VERA skill. Commands assume the
`vera` console script is available; substitute `python -m vera_cli` when needed.

## Build an effective query

Reduce a conversational question to document language:

- subject: `stormwater detention`, `restaurant parking`, `accessory dwelling`;
- action: `requirements`, `definition`, `exceptions`, `approval process`;
- constraint: section, district, jurisdiction, date, threshold, or facility;
- one or two common synonyms when terminology may vary.

Remove conversational framing such as "what does it say about." Split
multi-part questions into separate searches.

Examples:

| User question | Initial query |
| --- | --- |
| How much parking is required for restaurants? | `restaurant parking requirements minimum spaces` |
| Is EL-A a valid zoning district? | `EL-A zoning district` |
| Find the pipe sizing chart. | `pipe sizing chart table` with `--figures` |
| What must a site-plan submission contain? | `site plan submittal requirements` |

## Single-archive question answering

1. Search with hybrid retrieval:

   ```bash
   vera search "manual.vera" "restaurant parking requirements" --mode hybrid --top-k 5 --json
   ```

2. Read the text and heading of every plausible hit. Scores order candidates;
   they do not establish correctness.
3. If a hit contains an exception, definition, or cross-reference without its
   governing rule, rerun with `--context-chunks 1`.
4. Run a second targeted query when the first result does not directly answer
   every part of the question.
5. Answer with source, page, and heading citations.

Inspection is optional for simple Q&A. Use it first when the archive name is
ambiguous or the user asks about document identity:

```bash
vera inspect "manual.vera" --json
```

## Refine weak results

### Narrow broad results

Add the missing qualifier:

```text
<topic> minimum maximum threshold
<topic> exceptions exemptions
<topic> <district or facility type>
<section or table label> <topic>
```

Switch to keyword mode when exact language matters.

### Broaden sparse results

Change one dimension at a time:

1. remove a constraint;
2. replace a term with a likely synonym;
3. search the parent concept;
4. switch to semantic mode;
5. increase `--top-k` to 10.

Example expansion sequence:

```text
stormwater detention requirements
stormwater storage requirements
runoff control
post-development peak discharge
```

Record which queries and modes were attempted. This makes an
insufficient-evidence answer auditable.

## Exact phrases, codes, and identifiers

For section numbers, ordinance numbers, table labels, parcel IDs, model names,
acronyms, and short codes:

1. Search the exact value with keyword mode:

   ```bash
   vera search "manual.vera" "EL-A" --mode keyword --top-k 10 --json
   ```

2. Confirm the literal identifier appears in returned `text`; a relevant score
   alone is insufficient.
3. Search the identifier plus its subject, such as `EL-A zoning district`.
4. If punctuation is significant, remember that keyword tokenization removes
   punctuation during fallback. Do not conclude that a hyphenated identifier
   exists unless the returned text shows it.
5. If no literal match is returned, report that result and the searches tried.
   Do not bypass the CLI by querying the archive's SQLite tables directly.

## Compound questions

Search each issue separately and synthesize only after each has evidence.

For:

```text
What uses are permitted in C-2, and what parking is required for restaurants?
```

run:

```text
C-2 permitted uses
restaurant parking requirements
```

Keep each conclusion tied to its own citation. Do not use a result for one
sub-question as evidence for another.

## Figures, tables, charts, and maps

1. Search both the visual's likely title and its subject.
2. Add `--figures`:

   ```bash
   vera search "manual.vera" "pipe sizing chart" --top-k 5 --json --figures
   ```

3. Read the result text, caption, page, and surrounding heading.
4. Add `--context-chunks 1` if the caption lacks definitions, units, or scope.
5. Cite the caption and page.

Figure metadata does not include image bytes. State that the answer is based on
caption and nearby extracted text unless a separate vision-capable tool has
actually opened the image.

## Visual grounding

Add regions when a viewer must highlight the source text:

```bash
vera search "manual.vera" "detention requirements" --top-k 5 --json --regions
```

Each result's `regions` identify source blocks by page and bounding box. Regions
are block-granular, not necessarily word-precise. Preserve `page_width` and
`page_height` when transforming coordinates in a viewer.

## Directory and multi-archive search

Search a directory once rather than manually merging independent rankings:

```bash
vera search "./library" "insurance requirements" --top-k 10 --json
```

Each result includes `file`. Keep citations separated by archive and source
filename.

For a nested library without an index:

```bash
vera search "./library" "insurance requirements" --recursive --exclude "archive/**" --json
```

When sources disagree:

1. group evidence by archive;
2. compare scope, heading, date, jurisdiction, and defined terms;
3. explain only differences supported by retrieved text;
4. do not collapse conflicting requirements into one rule.

Suggested answer:

```text
Short answer: ...

By source:
- Source A: ... (source-a.pdf, p. 12, Eligibility).
- Source B: ... (source-b.pdf, pp. 44-45, Exceptions).

Gap or scope note: ...
```

## Indexed library workflow

Indexing writes local artifacts and should only be done when authorized.

1. Build once:

   ```bash
   vera index build "./library" --recursive --json
   ```

2. Search the directory normally. A fresh index is selected automatically.
3. Inspect `index.used`; if false, read `index.reasons`.
4. After adding, moving, replacing, or deleting archives:

   ```bash
   vera index status "./library" --json
   vera index update "./library" --json
   ```

`index status` exits 1 when stale or missing even though it emits a useful JSON
report. Search can safely fall back to direct file search when the index is not
fresh.

## Convert then search

Conversion writes archives; confirm that the user wants this change.

Single PDF:

```bash
vera convert "manual.pdf" "manual.vera" --json
vera validate "manual.vera" --json
vera search "manual.vera" "target question" --top-k 5 --json
```

Nested PDF library:

```bash
vera convert "./proposals" --recursive --json
vera index build "./proposals" --recursive --json
vera search "./proposals" "termination clause" --top-k 10 --json
```

Batch conversion skips existing outputs unless `--overwrite` is supplied.
Never add `--overwrite` without explicit authorization.

## Evidence quality

Strong evidence:

- directly states the answer;
- appears under the governing heading;
- includes the relevant threshold, definition, rule, step, or exception;
- is corroborated by nearby text or another result from the same section.

Weak evidence:

- shares only broad vocabulary;
- comes from an unrelated heading;
- mentions an exception without the main rule;
- omits the exact identifier;
- is only a caption when the question needs table cells or image content;
- conflicts with another result and the scope difference is unresolved.

Do not answer from weak evidence alone.

## Insufficient or conflicting evidence

Run at least one sensible refinement before declaring a gap. Then use:

```text
I did not find a direct statement that <claim>. I searched for <queries> using
<modes>. The closest evidence says <supported statement> (<source>, p. X,
<heading>). The archive does not provide enough evidence to conclude <claim>.
```

For conflict, cite both passages and state the unresolved issue. Do not invent a
priority rule, effective date, or scope distinction.

## Final response checklist

- Direct answer first when evidence supports one.
- Citation on every substantive document-backed claim.
- Exact terms and thresholds preserved.
- Source-specific conclusions kept separate.
- Search gaps and uncertainty stated explicitly.
- No claim of visual inspection based only on figure metadata.
