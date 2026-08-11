# Creating an ingest pipeline plugin

An ingest pipeline turns a source document into a normalized `IngestResult`
that shared conversion writes into a `.vera` archive. `vera-ingest-pymupdf`
and `vera-ingest-docling` are both ordinary plugins built on this contract —
nothing in `vera-ingest`, `vera-cli`, or `vera-app` special-cases either one.
Write your own to support a new source format, a different parsing engine, or
an experimental chunking strategy.

See [Architecture](architecture.md) for how pipeline packages fit into the
rest of VERA, and [Pipeline options](conversion.md#pipeline-options) for how
`--pipeline-option` and descriptors work from the user's side.

## The contract

A pipeline is any object with an `ingest` method matching this shape — there
is no base class to inherit from:

```python
class IngestPipeline(Protocol):
    def ingest(self, source_path: str, options: IngestRequest) -> IngestResult:
        ...
```

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
    coerce_ingest_request,
)

from .options import ExampleOptions


class ExamplePipeline:
    """Whole-file ingest pipeline for plain-text sources."""

    def ingest(self, source_path: str, options: IngestRequest) -> IngestResult:
        request = coerce_ingest_request(options)
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

`options.py` owns typed defaults, validation, and the descriptor other
pipelines use for CLI/GUI discovery (see [descriptors](#advertise-configuration-with-a-descriptor)).
Each field's `metadata` doubles as its descriptor entry, so a setting's key,
default, and presentation live in one place instead of three:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from vera_ingest.descriptors import PipelineCapabilities, PipelineDescriptor, fields_from_dataclass
from vera_ingest.option_parsing import (
    allowed_keys_from_dataclass,
    reject_unknown_keys,
    require_mapping,
    require_positive_int,
)


@dataclass(frozen=True)
class ExampleOptions:
    chunk_size: int = field(
        default=2000,
        metadata={
            "label": "Chunk size",
            "description": "Maximum characters kept from the file.",
            "minimum": 100,
        },
    )

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None = None) -> "ExampleOptions":
        data = reject_unknown_keys(
            require_mapping(raw, label="Example pipeline_options"),
            allowed=allowed_keys_from_dataclass(cls),
            label="Example",
        )
        return cls(
            chunk_size=require_positive_int(
                data.get("chunk_size", cls.chunk_size), name="chunk_size"
            )
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

`__init__.py` exposes the entry-point factories:

```python
from __future__ import annotations

from vera_ingest.descriptors import PipelineDescriptor
from vera_ingest.pipeline import UnknownIngestPipelineError

from .options import describe_pipeline
from .pipeline import ExamplePipeline

__all__ = ["ExamplePipeline", "create_pipeline", "create_descriptor"]


def create_pipeline(variant: str = "") -> ExamplePipeline:
    if variant not in {"", "default"}:
        raise UnknownIngestPipelineError(f"Unknown 'example' pipeline variant {variant!r}.")
    return ExamplePipeline()


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

## Try it without publishing a package

Entry points require an installed distribution. For a quick local experiment,
register a pipeline in-process instead — useful in a script, notebook, or
test, but only for the lifetime of that process. Both `register_ingest_pipeline`
and `register_ingest_pipeline_descriptor` also work as decorators when you
omit the factory argument:

```python
from vera_ingest.pipeline import register_ingest_pipeline, register_ingest_pipeline_descriptor
from vera_ingest import convert

from vera_ingest_example.pipeline import ExamplePipeline
from vera_ingest_example.options import describe_pipeline


@register_ingest_pipeline("example")
def create_pipeline(variant: str = "") -> ExamplePipeline:
    return ExamplePipeline()


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
without knowing anything provider-specific:

- `capabilities` (`PipelineCapabilities`) tells clients which legacy CLI
  aliases apply. `field_keys()` from your `fields` tuple determines which of
  `convert()`'s compatibility kwargs (`chunk_size`, `overlap`, `ocr_mode`, ...)
  get forwarded into `pipeline_options` for your provider — omit a field and
  that alias is silently dropped for you rather than leaking in unexpected.
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

Your pipeline's own `from_mapping` (as in `ExampleOptions` above) is still
responsible for validating whatever ends up in `pipeline_options` — the
descriptor is metadata for callers, not a validator VERA runs on your behalf.
`vera_ingest.option_parsing.allowed_keys_from_dataclass` keeps the "which keys
does `from_mapping` accept" list in sync with the same dataclass, for the same
reason.

## Validate and compare against a baseline

Test the pipeline directly first, without touching the registry:

```python
from vera_ingest.types import IngestRequest
from vera_ingest_example.pipeline import ExamplePipeline

result = ExamplePipeline().ingest("notes.txt", IngestRequest(pipeline_options={"chunk_size": 100}))
assert result.chunks
```

Then convert and inspect/validate the archive end to end:

```bash
vera convert "notes.txt" "notes.vera" --parser example
vera inspect "notes.vera" --json
vera validate "notes.vera" --json
```

To judge whether a new pipeline (or a chunking change within one) actually
retrieves better, run the same query set through `vera eval` against archives
produced by each pipeline and compare hit rate / MRR — see
[Evaluation](evaluation.md).

## Reference implementations

- [`vera-ingest-pymupdf`](packages/vera-ingest-pymupdf.md) — the simplest real
  pipeline: deterministic parsing, shared sliding-window chunking helpers
  (`vera_ingest.chunking`), selective Tesseract OCR. Start here.
- [`vera-ingest-docling`](packages/vera-ingest-docling.md) — a more involved
  pipeline: its own chunker, layout/table/figure mapping, and page-level
  failure recovery. Use it as a model once your pipeline needs more than the
  basics.

## See also

- [Architecture](architecture.md#vera-ingest) — package boundaries and where
  pipeline plugins fit.
- [Convert documents](conversion.md#pipeline-options) — the user-facing side
  of `--parser` and `--pipeline-option`.
- [`vera_ingest` API reference](reference/vera-ingest.md) — `IngestPipeline`,
  `IngestRequest`/`IngestResult`, registry, and descriptor types.
