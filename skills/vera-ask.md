---
name: vera-ask
description: Use when answering a user's question from one or more VERA (.vera) archives; guides query construction, iterative search expansion, evidence synthesis, and citation-ready responses using the vera skill.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [vera, retrieval, question-answering, semantic-search, citations, documents]
    related_skills: [vera]
---

# VERA Ask

## Overview

Use this skill to answer user questions from `.vera` archives with grounded, citation-ready responses. It is a workflow layer on top of the `vera` skill: load `vera` first for the exact CLI commands, local-path fallback, JSON output expectations, citation rules, and archive inspection/validation commands.

The goal is not to run one search and summarize the top hit. The goal is to translate the user's question into one or more effective VERA searches, expand or narrow those searches based on what comes back, verify enough evidence to answer, and clearly separate supported conclusions from gaps in the archive.

## When to Use

Use this skill when the user asks to:

- Answer a question from a `.vera` file or a set of `.vera` files.
- Compare requirements, definitions, thresholds, procedures, tables, figures, or policies in a VERA archive.
- Find where a document discusses a concept, term, section, code, acronym, phrase, or requirement.
- Produce a cited explanation, recommendation, checklist, or summary based on VERA search results.
- Troubleshoot an answer that seems unsupported, incomplete, or contradicted by another VERA hit.

Do not use this skill for converting PDFs or validating archive format unless that is a prerequisite to answering; use `vera` directly for conversion/inspection/validation tasks.

## Mandatory Dependency

Before using this workflow, load the `vera` skill:

```text
skill_view(name="vera")
```

Follow `vera` for:

- how to invoke the CLI on the current machine,
- `--json` output requirements,
- hybrid/keyword/semantic mode details,
- figure/table metadata handling,
- citation formatting,
- validation and inspection commands,
- pitfalls for short codes, hyphenated identifiers, and false-positive keyword hits.

## Default Answering Workflow

1. **Identify the archive(s) and the question.**
   - If the user supplied exactly one `.vera` path and a clear question, proceed.
   - If multiple archives are supplied, search each relevant archive and keep citations separated by source.
   - If no archive path is supplied and it cannot be discovered from context, ask for the `.vera` file path.

2. **Inspect when source identity matters.**
   - If the user asks what document an archive represents, if multiple archives have ambiguous names, or if you need page/chunk counts, run `vera inspect <file>.vera --json`.
   - You usually do not need inspection for a simple direct Q&A if the path and source are obvious.

3. **Build an initial high-recall query.**
   - Convert the user question into a concise natural-language query containing the core noun phrase, governing action, and any named entity.
   - Default to `--mode hybrid --top-k 5 --json`.
   - Add `--figures` if the question mentions or likely depends on tables, charts, maps, diagrams, images, drawings, captions, schedules, matrices, or visual layout.

4. **Read results critically.**
   - Check the command exit code before trusting output.
   - Identify whether top results actually answer the question or only contain related vocabulary.
   - Track page numbers, headings, source filenames, and relevant quoted language for citations.

5. **Expand, narrow, or switch modes as needed.**
   - If evidence is thin, broad, contradictory, or only partially responsive, run targeted follow-up searches before answering.
   - Use the expansion patterns below instead of guessing.

6. **Synthesize only from retrieved evidence.**
   - Use the strongest, most direct chunks first.
   - Reconcile conflicts by explaining scope, section, page, date, or terminology differences when the retrieved text supports that explanation.
   - If the archive does not contain enough evidence, say so and describe what was searched.

7. **Answer with citations.**
   - Every substantive claim from the document needs a citation.
   - Prefer a concise direct answer first, then bullets or explanation.
   - Include exact terms, thresholds, definitions, and page references when present.

## Building the Initial VERA Query

Start from the user's words, then normalize into search language likely to appear in the document.

### Include

- **Subject:** the thing being asked about, e.g. `stormwater detention`, `restaurant parking`, `accessory dwelling unit`.
- **Action or relationship:** `requirements`, `definition`, `allowed uses`, `minimum`, `exceptions`, `approval process`.
- **Constraints:** section number, district, jurisdiction, date, table name, threshold, material, facility type.
- **Synonyms if compact:** add one or two alternatives only when common, e.g. `retention detention`, `parking spaces minimum`.

### Exclude from the search string

- Politeness and conversational framing: `what does it say about`, `can you tell me`.
- Long multi-clause tasks that mix several questions. Split them into separate searches.
- Speculative terms not present in the user's question unless used in an expansion search.

### Query Templates

Use these as starting patterns:

```text
<topic> requirements
<topic> definition
<topic> exceptions
<topic> approval process
<district/code> permitted uses <use/topic>
<section number> <topic>
<table/schedule name> <topic>
<exact phrase or identifier>
```

Examples:

| User asks | Initial query |
|---|---|
| "How much parking is required for restaurants?" | `restaurant parking requirements minimum spaces` |
| "Is EL-A a valid zoning district?" | `EL-A zoning district` |
| "What does it say about detention ponds?" | `detention pond stormwater requirements` |
| "Find the pipe sizing chart" | `pipe sizing chart table` with `--figures` |
| "What are the submittal requirements for site plans?" | `site plan submittal requirements` |

## Choosing Search Mode

Default to `hybrid` for the first pass.

Use `keyword` when:

- the query contains quoted text,
- the user asks for an exact phrase,
- searching section numbers, ordinance numbers, table labels, figure labels, model names, parcel IDs, or zoning codes,
- the semantic result seems related but does not contain the exact identifier.

Use `semantic` when:

- the user is asking conceptually or with paraphrased language,
- keyword/hybrid results miss because the document uses different wording,
- the question asks for intent, purpose, process, or explanation rather than exact terms.

Use multiple modes when confidence matters. A strong answer often starts with hybrid, then checks keyword for exact language or semantic for alternate wording.

## Search Expansion Strategy

Run follow-up searches when the first results are weak, incomplete, too broad, contradictory, or lack the exact terms needed.

### 1. Narrow an over-broad result set

If results discuss the broad topic but not the specific question, add qualifiers:

```text
<topic> <specific requirement>
<topic> <district/use/type>
<topic> minimum maximum threshold
<topic> exceptions exemptions
<section/table> <topic>
```

Increase precision with `--mode keyword` for exact terms.

### 2. Broaden a sparse result set

If few or no useful hits appear:

- remove one constraint at a time,
- replace specific wording with a synonym,
- search the parent concept,
- switch to `--mode semantic`,
- increase `--top-k` to 10 for broad exploratory questions.

Examples:

```text
stormwater detention
stormwater management storage
runoff control requirements
post-development peak discharge
```

### 3. Search exact language separately

For definitions, codes, section numbers, acronyms, and short identifiers:

1. Search the exact term with `--mode keyword`.
2. Inspect the returned chunk text to confirm the exact term appears.
3. If tokenization may create false positives, follow the `vera` skill's SQLite/regex fallback guidance before concluding the identifier exists or does not exist.

### 4. Split compound questions

If the user asks multiple things, run separate searches and answer in sections.

Example user question:

```text
What are the permitted uses in C-2, and what parking is required for restaurants?
```

Search separately:

```text
C-2 permitted uses
restaurant parking requirements
```

### 5. Use headings and pages from good hits

When a hit identifies a promising heading, table, or page range, search within that vocabulary next:

```text
<heading phrase> <specific topic>
<table title> <row/column/topic>
```

If the `vera` skill exposes page retrieval in the active environment, retrieve nearby page context when a single chunk appears truncated or references preceding/following text.

### 6. Include figures and tables deliberately

For tables/charts/figures:

- add `--figures`,
- search both the caption/table title and the concept,
- cite figure or table caption/page when available,
- do not claim to inspect pixels unless an image asset was actually extracted and viewed with a vision-capable tool.

## Multi-Archive Questions

When answering from several `.vera` files:

1. Run the same initial query against each archive, unless the user scoped the question to one source.
2. If one archive uses different terminology, adapt expansion queries for that source.
3. Keep notes per source: best hits, pages, headings, and whether the archive lacked evidence.
4. In the final answer, cite each source separately and avoid merging conflicting requirements as if they came from one document.

Recommended response structure:

```text
Short answer: ...

By source:
- Source A: ... (source-a.pdf, p. 12)
- Source B: ... (source-b.pdf, pp. 44-45)

Notes/gaps: ...
```

## Evidence Quality Heuristics

Treat a result as strong evidence when it:

- directly contains the answer language,
- comes from a relevant heading/section/table,
- includes a definition, requirement, threshold, procedure step, or exception text,
- is corroborated by another nearby or same-section hit.

Treat a result as weak evidence when it:

- only shares generic words with the query,
- is from an unrelated heading,
- mentions an exception without the main rule,
- lacks the exact code/identifier being asked about,
- is a figure caption without surrounding explanatory text,
- conflicts with another result and you have not resolved scope.

Do not answer from weak evidence alone. Search again or state that the archive does not provide a clear answer.

## Response Requirements

A good VERA-backed answer should include:

- **Direct answer first.** Start with the conclusion if evidence supports it.
- **Citations on claims.** Cite source filename, page/page range, and heading when available.
- **Key quoted terms.** Preserve exact defined terms, thresholds, and requirement language.
- **Scope and caveats.** Mention when a rule applies only to a district, facility type, chapter, date, or condition.
- **Search gap disclosure.** If no direct answer was found, say what searches/modes were tried and what related evidence was found.

Suggested format:

```text
Short answer: <answer> (<source>, p. X, <heading>).

Details:
- <claim/evidence> (<source>, p. X).
- <claim/evidence> (<source>, pp. X-Y).

Caveat: <scope limitation or missing evidence, if any>.
```

For uncertain or negative answers:

```text
I did not find a direct statement that <claim>. I searched for <terms/modes>. The closest relevant evidence says <related evidence> (<source>, p. X). Based on that, <careful conclusion or next step>.
```

## Common Pitfalls

1. **Using the user's full sentence as the only query.** Rewrite it into concise document terms, then expand.
2. **Stopping after one hybrid search.** If results are not directly responsive, search again with keyword, semantic, synonyms, or narrower terms.
3. **Treating top-ranked as true.** Scores rank relevance, not correctness. Read the text and heading.
4. **Missing exact identifiers.** Short codes and hyphenated terms need keyword verification and sometimes regex/SQLite fallback per the `vera` skill.
5. **Forgetting tables/figures.** Use `--figures` for table/chart/map/diagram/caption questions.
6. **Over-citing a broad page.** Cite the most specific page/heading available for each claim.
7. **Inventing missing context.** If retrieved chunks do not answer the question, say what is missing and offer the closest supported evidence.
8. **Blending sources.** In multi-archive answers, keep each source's requirements separate unless the documents themselves establish a relationship.

## Verification Checklist

- [ ] Loaded and followed the `vera` skill for CLI syntax and citation rules.
- [ ] Identified the `.vera` archive(s) and the user's actual question.
- [ ] Built a concise initial query from topic + action + constraints.
- [ ] Used `hybrid` first unless exact terms or conceptual paraphrase justified another mode.
- [ ] Used `keyword` for exact phrases, identifiers, section numbers, and codes.
- [ ] Used `semantic` or synonyms when wording mismatch was likely.
- [ ] Expanded/narrowed search when first results were weak or incomplete.
- [ ] Added `--figures` for table/chart/map/diagram/image/caption questions.
- [ ] Checked command exit codes and did not trust failed output.
- [ ] Cited every substantive document-backed claim.
- [ ] Explicitly stated gaps, uncertainty, or lack of direct evidence when applicable.