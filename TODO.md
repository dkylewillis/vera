# TODO: Harden PDF directory conversion and library loading

## Problem

PDF Directory conversion can publish `.vera` files that contain no searchable
chunks (commonly scanned PDFs without OCR). Interrupted or failed conversions
may also leave incomplete SQLite files. Opening a library later inspects these
files and can fail with `no such table: vera_metadata`.

## Context and root cause

This was found while opening the indexed library at:

`C:\Users\kwillis\Desktop\Engineering\Contracts\Work Authorizations`

The library index itself was structurally healthy. Its active generation had
the expected library-index tables, including `index_metadata`, and contained
1,154 indexed documents. A library index intentionally does not contain
`vera_metadata`; that table belongs in each source `.vera` document.

The failure came from source documents in the library:

- 200 `.vera` files were rejected by the index with `No chunks found`. These
  appear to correspond largely to scanned PDFs. The current PyMuPDF parser does
  not perform OCR, but conversion can still report success and publish a
  database with no searchable chunks.
- Six source files lacked `vera_metadata`, indicating incomplete or otherwise
  malformed SQLite outputs. An interrupted write is one possible cause because
  conversion currently writes directly to the final destination instead of
  publishing atomically.
- Batch conversion skips any existing destination when overwrite is disabled,
  without validating it. Once a malformed output exists, later batch runs can
  preserve it indefinitely.
- Opening a folder calls corpus inspection across discovered `.vera` files.
  Corpus inspection does not isolate invalid documents, so one malformed file
  can abort loading the entire library even when a healthy index exists and
  already records that some files were skipped.

The `.vera-index` directory should not be opened as a document or library
itself; callers should open its parent library directory. However, opening the
parent directory must remain safe when individual conversions fail.

## Work

- [x] Make `convert()` write to a temporary sibling file, validate the completed
      database, and atomically replace the destination only after validation.
      Delete the temporary file after any failure.
- [x] Treat conversion with no searchable text/chunks as a failure with a clear
      message that the PDF may be scanned and requires OCR.
- [x] In batch conversion, validate existing `.vera` outputs before classifying
      them as `skipped_existing`; report malformed existing outputs separately.
- [x] Make corpus inspection and fallback search skip invalid `.vera` files
      rather than failing the entire library. Include file paths and validation
      reasons in inspection/search metadata.
- [x] Ensure library indexes retain and report skipped-file reasons without
      attempting to open those files during inspection.
- [x] Add tests for textless scanned-PDF output, interrupted conversion,
      malformed existing output, mixed valid/invalid libraries, and indexed
      libraries containing skipped files.
- [x] Update the README, user documentation, agent skill/reference material,
      examples, and documentation-contract tests for all changed CLI/JSON
      behavior.
- [ ] Run the complete test suite and verify `vera index build`, `index update`,
      folder inspection, and indexed/fallback search against a mixed library.

## Reproduction data

The affected library had 1,154 indexed files and 201 skipped files. Of the
skipped files, 200 reported `No chunks found`; six files currently lacked the
`vera_metadata` table. Rebuild the index after repairing or removing malformed
outputs.
