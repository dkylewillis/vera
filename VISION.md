# VERA Vision

This file describes what VERA is meant to become and the principles that
should guide design decisions. It is direction, not a feature list.
[ROADMAP.md](ROADMAP.md) tracks concrete work items; the
[README](README.md) and [docs](docs/index.md) describe what ships today.

## The problem

Semantic search over documents should be easy. Today it usually means
standing up a vector database, writing an ingestion pipeline, choosing a
chunker and an embedding model, and keeping all of it in sync with the
documents. That is too much machinery for "find the answer in this manual."

VERA removes that machinery. A user should not need to know what a
collection, vector store, ingestion pipeline, or metadata schema is.

## Principles

### 1. Convert once, search anywhere

The expensive work (parsing, OCR, chunking, embedding) happens once, at
conversion. The result is a single portable `.vera` file that carries its
chunks, embeddings, keyword index, citations, and original source. Search
only embeds the query.

This matters most for the smallest case: handing one document to an AI
agent as context. Re-chunking and re-embedding a document on every use is
wasteful. A `.vera` file is ready the moment it is opened, with no server,
no API call, and no database to run.

### 2. One document to thousands, same interface

The same commands and tools work on one archive, a folder of tens of
archives, or a library of thousands. Small cases need no setup. Large cases
add an optional, rebuildable index for speed, never a different workflow.
The `.vera` archives stay the source of truth; any index is a cache.

### 3. The filesystem is the database interface

> Your folders define the library. Your files define its contents.
> VERA makes them searchable.

Users organize documents the way they always have, in folders. VERA makes
that existing hierarchy searchable instead of asking users to migrate into a
new document management system. Someone with 10,000 documents spread across
years of project folders should be able to point VERA at the parent
directory and search.

Normal file operations become library operations:

| User action | VERA behavior |
|---|---|
| Add a document | Convert and index it |
| Delete a document | Remove its managed archive (recoverably; see below) |
| Replace a document | Reconvert only that document |
| Rename a document | Update its identity and path mapping |
| Move a document to another folder | Update its organization and search scope |
| Create a subfolder | Create a new searchable grouping |
| Move the whole library | Keep working, because paths are relative |

Folder structure becomes searchable metadata automatically. "Search only
documents under `Projects/Roundabout`" should be a folder-scoped retrieval,
not a collection the user had to create or tags they had to apply.

Changes made through File Explorer, scripts, or other applications must be
respected. VERA adds search and AI capability to the filesystem; it does not
replace the filesystem.

Requirements that follow from this:

- **Correctness over responsiveness.** Use filesystem watchers for fast
  updates, but periodically reconcile against the actual directory contents.
  Watchers miss events, especially on network drives and while the app is
  closed.
- **No silent data loss.** Deleting a source document must not destroy the
  only retained copy without a recovery path.
- **Everything derived is rebuildable** from the source documents and their
  archives.

### 4. Ingestion and embeddings are replaceable

Document parsing and embedding models improve quickly. VERA should let users
adopt better technology without changing how they search.

- Parsing, OCR, layout analysis, and chunking live in pluggable ingest
  pipelines. Advanced parsers (IBM Docling today; NVIDIA NeMo Retriever /
  nv-ingest and similar layout and table engines in the future) should plug in
  as pipelines beside the lightweight default.
- Embedding models are pluggable providers, local or hosted.
- Every archive records which pipeline and model produced it, so search uses
  the right query embedder and nothing is silently mislabeled.
- Upgrading means reconverting from the stored original. Upgrades should be
  incremental, so a library can move one document or one folder at a time.

### 5. Built for AI agents as well as people

Agents are first-class users. Every operation has machine-readable output
and an MCP tool, every result carries citations (page, heading, region), and
answers should be grounded in retrievable source text.

### 6. Local-first

Core conversion and search work offline with no API key. Hosted parsers,
embedders, and answer models are opt-in.

## Where this stands

Already in place: portable `.vera` archives, single-file and folder search,
recursive discovery with `--include` / `--exclude` path scoping, a rebuildable
library index, pluggable ingest pipelines (PyMuPDF, Markdown, Docling) and
embedding providers (hashing, MiniLM, OpenAI), desktop folder watching, and
managed libraries.

A managed library is a normal folder of source documents. VERA keeps mirrored
archives in a hidden `.vera/` folder (`archives/` mirrors the source tree and
keeps the source extension, `index/` replaces `.vera-index/`, and `trash/`
holds deleted archives for 30 days). Sync follows adds, edits, renames,
moves, and deletes. The nearest parent `.vera/` owns a folder, and searching
a subfolder scopes to that subfolder. `vera convert file.pdf` still writes a
sibling archive. Plain folders of `.vera` files still search as before.
Shared network libraries are still ahead.
