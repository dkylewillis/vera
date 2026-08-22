# Creating an ingest pipeline plugin

An ingest pipeline turns a source document into a normalized `IngestResult`
that shared conversion writes into a `.vera` archive. `vera-ingest-pymupdf`
and `vera-ingest-docling` are both ordinary plugins built on this contract —
nothing in `vera-ingest`, `vera-cli`, or `vera-app` special-cases either one.
Write your own to support a new source format, a different parsing engine, or
an experimental chunking strategy. Name the package after the engine
(`vera-ingest-example`), not the file type; advertise extensions on
`PipelineCapabilities.source_formats`. Planned non-PDF ingest and Markdown
grounding are in [Additional source formats and visual grounding](multi-format-ingest.md).

Registry and descriptor APIs (`register_ingest_pipeline`,
`register_ingest_pipeline_descriptor`, `PipelineDescriptor`, and related
discovery helpers) are experimental and may change before 1.0.

See [Architecture](architecture.md) for how pipeline packages fit into the
rest of VERA, and [Pipeline options](conversion.md#pipeline-options) for how
`--pipeline-option` and descriptors work from the user's side.

## The contract

A pipeline is any callable matching this shape — a plain function, or an
object implementing `__call__` if it needs to hold state. There is no base
class to inherit from:

```python
IngestPipeline = Callable[[str, IngestRequest], IngestResult]
```

For pre-0.3.x plugins, an object exposing a callable `ingest(self, source_path,
options)` method still works too — `vera_ingest.pipeline.invoke_ingest_pipeline`
calls that method when present and falls back to calling the pipeline itself
otherwise. New pipelines should prefer a plain callable; see
[reference implementations](#reference-implementations) below for when a
class (with `__call__`) is still the right choice.

`IngestRequest` carries the resolved `variant`, a cancellation token, and an
opaque `pipeline_options` mapping your pipeline owns and validates itself.
`IngestResult` returns:

- `pages` — one `ParsedPage` per page (`page_number`, `width`, `height`, `text`);
- `blocks` — one `IngestBlock` per layout unit (`block_id`, `page_number`,
  `block_type`, `text`, optional `bbox`/`heading_level`/image bytes/`regions`);
- `chunks` — one `IngestChunk` per retrievable unit (`chunk_id`, `text`,
  `page_start`/`page_end`, `heading_path`, `token_count`, `block_ids`);
- `parser_name`, `parser_version`, `chunking_strategy` — recorded in archive
  metadata for `vera inspect`;
- `diagnostics` — free-form dict recorded under archive metadata `"ocr"`.

Shared conversion enforces a few invariants on the result before writing it:
block and chunk IDs must be non-empty and unique, every chunk's `block_ids`
must reference a real block, and every chunk's `text` must be non-empty.
Image blocks with `image_bytes` are stored as figure attachments. Convert
associates those attachments with search hits only through `chunk.block_ids`,
so include each image block ID on a nearby same-page chunk or figures are
saved but omitted from `--figures`.

Parsers often emit `ParsedBlock` (the same layout fields without a stable
`block_id`). Convert with `IngestBlock.from_parsed(block_id, block)` before
returning `IngestResult.blocks`. Pipelines that mint IDs while parsing can
construct `IngestBlock` directly.

## Reusable chunking helpers

`vera_ingest.chunking` counts whitespace-split words, not characters.

- `build_chunks_from_blocks` — heading-aware sliding windows over
  `(block_id, ParsedBlock | IngestBlock)` pairs. PyMuPDF uses this; custom
  pipelines with structured layout should too.
- `chunk_pages` / `detect_heading` — public helpers for custom pipelines that
  only have `ParsedPage.text`. First-party pipelines do not call them.

Both sliding-window helpers clamp `overlap` to `chunk_size - 1` so carry never
overruns. PyMuPDF's descriptor still advertises overlap `maximum` 1000, which
can exceed a small `chunk_size`; the clamp is the runtime constraint.

## Minimal example

This plugin ingests plain-text files as a single page/block/chunk — enough to
exercise the full contract without a parsing dependency.

```text
vera-ingest-example/
  pyproject.toml
  src/vera_ingest_example/
    __init__.py
    options.py
    pipeline.py
```

`pipeline.py`:

```python
from __future__ import annotations

from pathlib import Path

from vera_ingest.types import (
    IngestBlock,
    IngestChunk,
    IngestRequest,
    IngestResult,
    ParsedPage,
    ensure_ingest_request,
)

from .options import ExampleOptions


def example_pipeline(source_path: str, options: IngestRequest) -> IngestResult:
    """Whole-file ingest pipeline for plain-text sources."""
    request = ensure_ingest_request(options)
    config = ExampleOptions.from_mapping(request.pipeline_options)
    text = Path(source_path).read_text(encoding="utf-8", errors="replace")

    block = IngestBlock(
        block_id="block_000001",
        page_number=1,
        block_type="paragraph",
        text=text,
    )
    chunk = IngestChunk(
        chunk_id="chunk_000001",
        text=text[: config.chunk_size] if config.chunk_size else text,
        page_start=1,
        page_end=1,
        heading_path="",
        token_count=len(text.split()),
        block_ids=[block.block_id],
    )

    return IngestResult(
        pages=[ParsedPage(page_number=1, width=None, height=None, text=text)],
        blocks=[block],
        chunks=[chunk],
        parser_name="example",
        parser_version="0.1.0",
        chunking_strategy="whole_file",
    )
```

`options.py` has two jobs: validate a raw `pipeline_options` dict into a typed
config (`from_mapping`), and describe that same config for CLI/GUI discovery
(`describe_pipeline`, see [descriptors](#advertise-configuration-with-a-descriptor)).
Doing both from *one* dataclass — instead of writing every setting's name,
default, and description out twice — is what `dataclasses.field(metadata=...)`
buys you below: `metadata` is a plain dict dataclasses let you attach to a
field; it does nothing on its own, but `fields_from_dataclass` (used in
`describe_pipeline`) reads it back out to build the descriptor, and
`vera_ingest.pipeline_options.PipelineOptions` reads the *same* metadata to
validate `pipeline_options` — so a straightforward pipeline like this one
doesn't need to write `from_mapping` at all:

```python
from __future__ import annotations

from dataclasses import dataclass, field

from vera_ingest.descriptors import PipelineCapabilities, PipelineDescriptor, fields_from_dataclass
from vera_ingest.pipeline_options import PipelineOptions


@dataclass(frozen=True)
class ExampleOptions(PipelineOptions):
    # `default=2000` is the real dataclass default. `metadata={...}` is
    # inert until something reads it: `fields_from_dataclass` (used in
    # `describe_pipeline` below) reads it to build the CLI/GUI descriptor,
    # and the inherited `from_mapping` reads it to validate `pipeline_options`.
    chunk_size: int = field(
        default=2000,
        metadata={
            "label": "Chunk size",
            "description": "Maximum characters kept from the file.",
            "minimum": 100,
            "maximum": 3000,
        },
    )


def describe_pipeline(variant: str = "") -> PipelineDescriptor:
    return PipelineDescriptor(
        provider="example",
        variant="",
        spec="example",
        label="example — plain-text pipeline",
        description="Whole-file ingest for plain-text sources.",
        capabilities=PipelineCapabilities(
            chunk_unit="characters",
            overlap_supported=False,
            ocr_supported=False,
            ocr_dpi_supported=False,
            source_formats=("txt",),
        ),
        fields=fields_from_dataclass(ExampleOptions),
    )
```

Traced through concretely:

- `ExampleOptions.from_mapping(None)` → `ExampleOptions(chunk_size=2000)` (falls
  back to the dataclass default).
- `ExampleOptions.from_mapping({"chunk_size": 500})` → `ExampleOptions(chunk_size=500)`.
- `ExampleOptions.from_mapping({"chunk_size": 0})` → raises `ValueError`
  (`"chunk_size must be between 100 and 3000"`) — `from_mapping` enforces
  advertised `metadata["minimum"]` / `metadata["maximum"]`, not just
  "must be a positive integer."
- `ExampleOptions.from_mapping({"chunk_size": 99999})` → the same range error.
- `ExampleOptions.from_mapping({"typo": 1})` → raises `ValueError`
  (`"Unknown Example option(s): 'typo'"`), since `"typo"` isn't a real field.
- `fields_from_dataclass(ExampleOptions)` walks the one `chunk_size` field and
  returns one `PipelineField(key="chunk_size", type="integer", default=2000,
  label="Chunk size", description="Maximum characters kept from the file.",
  minimum=100, maximum=3000)` — `key`/`type`/`default` came from the field
  itself (`type` inferred from the `int` annotation); only the human-facing
  `label`, `description`, and bounds needed to be spelled out, and only once.

### When *not* to inherit `PipelineOptions`

`PipelineOptions.from_mapping` only knows how to validate four field shapes:
a `bool`, an `int` (bounded by `metadata["minimum"]` / `metadata["maximum"]`
when those are set; otherwise non-negative), a `str` restricted to
`metadata["choices"]` (unless `allow_custom` is set), or free-text `str`. Both
real pipelines (`vera-ingest-pymupdf`, `vera-ingest-docling`) fit entirely
within those four shapes and inherit `PipelineOptions` as-is, with no
`from_mapping` of their own. If a future field ever needs something those four shapes can't express
— type conversion beyond bool/int/str, a cross-field check, or normalizing a
value rather than just validating it — override `from_mapping` on your own
subclass and write it with the `vera_doc.option_parsing` helpers directly,
the same way both plugins' `Options` classes worked before `PipelineOptions`
existed. Two class attributes cover the common customizations without an
override: `options_label` (the name used in error messages) and
`ignored_keys` (legacy `pipeline_options` keys to silently drop instead of
rejecting as unknown — see `DoclingOptions.ignored_keys` for `overlap`/
`ocr_dpi`, PyMuPDF-only legacy CLI aliases Docling doesn't have fields for).
`prepare_pipeline_options` also withholds Tesseract-shaped convert()/CLI
aliases (`ocr_language`, `ocr_dpi`, `ocr_download`) when
`capabilities.ocr_engine` is not `"tesseract"`, even if the plugin advertises
an `ocr_language` field with a different vocabulary (Docling/RapidOCR).

`__init__.py` exposes the entry-point factories. `create_pipeline` returns the
bare function itself — there's nothing to instantiate:

```python
from __future__ import annotations

from vera_ingest.descriptors import PipelineDescriptor
from vera_ingest.pipeline import IngestPipeline, UnknownIngestPipelineError

from .options import describe_pipeline
from .pipeline import example_pipeline

__all__ = ["create_descriptor", "create_pipeline", "example_pipeline"]


def create_pipeline(variant: str = "") -> IngestPipeline:
    if variant not in {"", "default"}:
        raise UnknownIngestPipelineError(f"Unknown 'example' pipeline variant {variant!r}.")
    return example_pipeline


def create_descriptor(variant: str = "") -> PipelineDescriptor:
    return describe_pipeline(variant)
```

`pyproject.toml` registers both under VERA's entry-point groups:

```toml
[project]
name = "vera-ingest-example"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = ["vera-ingest"]

[project.entry-points."vera.ingest_pipelines"]
example = "vera_ingest_example:create_pipeline"

[project.entry-points."vera.ingest_pipeline_descriptors"]
example = "vera_ingest_example:create_descriptor"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

Install it editable and it's immediately available by name:

```bash
python -m pip install -e ./vera-ingest-example
vera convert "notes.txt" "notes.vera" --parser example
vera convert "notes.txt" "notes.vera" --parser example --pipeline-option chunk_size=500
```

An unresolved `--parser` name fails before parsing and lists installed
providers, which doubles as a quick check that discovery picked up your
plugin:

```text
Unknown ingest parser pipeline 'example'. Installed providers: docling, pymupdf.
```

A broken entry point does not raise during discovery. Import failures are
logged as warnings and omitted from that installed-providers list. Inspect
them with `list_ingest_pipeline_load_errors()` after `list_ingest_pipelines()`
is empty of your provider, then fix the import and restart the process
(entry-point load errors are recorded once until
`reset_ingest_pipeline_registry()`).

## Try it without publishing a package

Entry points require an installed distribution. For a quick local experiment,
register a pipeline in-process instead — useful in a script, notebook, or
test, but only for the lifetime of that process. Both `register_ingest_pipeline`
and `register_ingest_pipeline_descriptor` also work as decorators when you
omit the factory argument:

```python
from vera_ingest.pipeline import register_ingest_pipeline, register_ingest_pipeline_descriptor
from vera_ingest import convert

from vera_ingest_example.pipeline import example_pipeline
from vera_ingest_example.options import describe_pipeline


@register_ingest_pipeline("example")
def create_pipeline(variant: str = "") -> IngestPipeline:
    return example_pipeline


register_ingest_pipeline_descriptor("example", describe_pipeline)

convert("notes.txt", "notes.vera", parser="example")
```

Pass `replace=True` (`@register_ingest_pipeline("example", replace=True)`, or
the equivalent plain-call form) if you're iterating on the same provider name
across repeated calls, for example in a REPL.

## Advertise configuration with a descriptor

A `PipelineDescriptor` (returned by `describe_pipeline`/`create_descriptor`)
is what lets generic code — `vera convert`'s help text, the desktop app's
`PipelineConfigForm`, `vera inspect` — describe your pipeline's settings
without knowing anything provider-specific. Keep the package import and
`create_descriptor` free of optional runtime libraries so discovery can
advertise the pipeline without importing optional runtime dependencies.
`vera-ingest-docling` sets `installed=False` when `docling` / `docling_core`
are missing, so Convert shows the install hint instead of a plugin load error.

- `capabilities` (`PipelineCapabilities`) tells clients which legacy CLI
  aliases apply. `field_keys()` from your `fields` tuple determines which of
  `convert()`'s compatibility kwargs (`chunk_size`, `overlap`, `ocr_mode`, ...)
  get forwarded into `pipeline_options` for your provider — omit a field and
  that alias is silently dropped for you rather than leaking in unexpected.
  Omitted `convert()` kwargs (Python API `None` defaults) are not forwarded
  at all, so your `Options` defaults apply; the CLI still passes its argparse
  defaults.
- `fields` (`PipelineField` tuple) drives generated forms: type, default,
  bounds, and enum choices.

`vera_ingest.descriptors.fields_from_dataclass` builds that `fields` tuple
directly from your `Options` dataclass instead of a hand-maintained, parallel
list: a field's `key` and `default` come from the dataclass field itself, and
its `metadata` mapping supplies the rest (`label`, `description`, `unit`,
`minimum`/`maximum`/`step`, `choices`, `allow_custom`, `placeholder`). A
field's `type` is inferred from its annotation (`int` → `"integer"`, `bool` →
`"boolean"`, `str` → `"string"`) unless `metadata["type"]` overrides it — used
for `"enum"` fields, which are plain `str` at the type level but have a fixed
`choices` list. A dataclass field with no `metadata` is treated as internal
and omitted from the descriptor. `vera-ingest-pymupdf` and
`vera-ingest-docling` both build their descriptors this way — see their
`options.py` for larger examples with `enum` and `boolean` fields.

`from_mapping` (inherited from `PipelineOptions` in `ExampleOptions` above,
or written by hand for pipelines that need more) is what validates
`pipeline_options`, using the same field `metadata` — including
`minimum`/`maximum` — that `fields_from_dataclass` copies into the descriptor
for CLI/GUI forms.

## Validate and compare against a baseline

Test the pipeline directly first, without touching the registry:

```python
from vera_ingest.types import IngestRequest
from vera_ingest_example.pipeline import example_pipeline

result = example_pipeline("notes.txt", IngestRequest(pipeline_options={"chunk_size": 100}))
assert result.chunks
```

Then convert and inspect/validate the archive end to end:

```bash
vera convert "notes.txt" "notes.vera" --parser example
vera inspect "notes.vera" --json
vera validate "notes.vera" --json
```

For a visual layout check against a PDF pipeline, use the contributor
[`vera-lab`](packages/vera-lab.md) tool (workspace `dev` extra). It runs the
pipeline without writing an archive and emits an HTML report with block/chunk
overlays and layout lint:

```bash
vera-lab "manual.pdf" -o report.html --parser pymupdf
vera-lab "manual.pdf" -o compare.html --parser pymupdf --parser docling
```

## Desktop app plugins

Source-run and packaged builds use one sidecar interpreter. Extra ingest and
embedding plugins are pip packages in **the same environment**.

1. Install `vera-doc` and `vera-ingest` 0.3.x plus your plugin
   (`python -m pip install …` or `python -m pip install -e <clone>`). From a
   checkout, `uv sync --extra app --extra onnx` covers the desktop
   sidecar MiniLM path. Add `--extra ml` for other Sentence Transformers
   models and `--extra docling` only for CLI Docling tests.
2. Install every import the sidecar will need in that interpreter. MiniLM
   (`onnxruntime` + `tokenizers`) is the `onnx` extra for CLI and
   source-run (`uv sync --extra onnx`). The packaged desktop app already
   freezes it and vendors a VERA-exported MiniLM graph;
   hashing needs no extra install. Other Hub Sentence Transformers models
   still need `uv sync --extra ml`.
3. Restart the desktop app so Convert reloads `describe_ingest_pipelines`.
   Bundled `pymupdf` wins on duplicate names. The 0.3.0 sidecar does not list
   `docling`. Raw `PYTHONPATH`
   folders are not discovered.

See [Plugins in the same environment](desktop-app-getting-started.md#plugins-in-the-same-environment).

To judge whether a new pipeline (or a chunking change within one) actually
retrieves better, run the same query set through `vera eval` against archives
produced by each pipeline and compare hit rate / MRR — see
[Evaluation](evaluation.md).

## Reference implementations

- [`vera-ingest-pymupdf`](packages/vera-ingest-pymupdf.md) — the simplest real
  pipeline: a plain `pymupdf_pipeline(source_path, options)` function,
  deterministic parsing, shared sliding-window chunking
  (`build_chunks_from_blocks`; `chunk_pages` is available for custom
  page-text pipelines),
  selective Tesseract OCR — and its `PyMuPDFOptions`
  inherits `PipelineOptions` for `from_mapping`, same as this guide's example.
  Start here.
- [`vera-ingest-docling`](packages/vera-ingest-docling.md) — a more involved
  pipeline: `DoclingHybridPipeline` is a class implementing `__call__`
  (needed because its recovery/fallback logic is decomposed into helper
  modules — `mapping.py`, `converter.py`, `recovery.py` — not because it
  holds state across calls), with its own chunker, layout/table/figure
  mapping, and page-level failure recovery.
  `DoclingOptions` inherits `PipelineOptions` too, using `ignored_keys` for
  the PyMuPDF-only legacy aliases it doesn't support. Use it as a model once
  your pipeline needs more than a single function.

## See also

- [Architecture](architecture.md#vera-ingest) — package boundaries and where
  pipeline plugins fit.
- [Convert documents](conversion.md#pipeline-options) — the user-facing side
  of `--parser` and `--pipeline-option`.
- [Additional source formats and visual grounding](multi-format-ingest.md) —
  planned non-PDF ingest, `source_formats`, and Markdown/PDF viewer surfaces.
- [`vera_ingest` API reference](reference/vera-ingest.md) — `IngestPipeline`,
  `IngestRequest`/`IngestResult`, registry, and descriptor types.
