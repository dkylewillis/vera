# Creating an ingest pipeline plugin

`vera-ingest` bundles the `pymupdf` parser. Extra parsers register as ordinary
Python packages so the CLI and desktop app can discover them at runtime.

## Entry points

A plugin publishes two setuptools entry points:

```toml
[project.entry-points."vera.ingest_pipelines"]
example = "my_vera_plugin:create_pipeline"

[project.entry-points."vera.ingest_pipeline_descriptors"]
example = "my_vera_plugin:create_descriptor"
```

The entry-point name is the provider (`example`). Users select it with
`--parser example` or `--parser example:variant`.

## Factories

`create_pipeline(variant)` must return a callable
`(source_path, output_path, **options) -> str` or an object with a matching
`convert()` method. The return value is the output `.vera` path.

`create_descriptor(variant)` must return a
`vera_ingest.pipeline.PipelineDescriptor`.

```python
from vera_ingest.pipeline import PipelineDescriptor, UnknownIngestPipelineError

def create_pipeline(variant: str = ""):
    if (variant or "").strip().lower() not in {"", "default"}:
        raise UnknownIngestPipelineError(
            f"Unknown example pipeline variant {variant!r}; use 'example'."
        )

    def ingest(source_path: str, output_path: str, **options) -> str:
        # Parse, chunk, write, and validate a .vera archive, then return output_path.
        return output_path

    return ingest

def create_descriptor(variant: str = "") -> PipelineDescriptor:
    return PipelineDescriptor(
        provider="example",
        spec="example",
        label="example — custom parser",
        description="Example ingest plugin.",
        installed=True,
    )
```

Known convert options include `model`, `chunk_size`, `overlap`,
`store_original`, `ocr_mode`, `ocr_language`, `ocr_dpi`, and `cancel`. Plugins
may ignore options they do not implement.

## Install

Published package:

```bash
python -m pip install my-vera-plugin
vera convert "input.pdf" --parser example
```

Cloned repository (editable, keeps source in the clone):

```bash
git clone https://github.com/example/my-vera-plugin.git
python -m pip install -e ./my-vera-plugin
vera convert "input.pdf" --parser example
```

Editable installs create distribution metadata, which is what
`importlib.metadata` uses to find entry points. Adding a clone to
`PYTHONPATH` without installing it is not enough.

The selected environment must provide `vera-ingest` 0.2.x (plugin API version
1). Confirm discovery with:

```python
from vera_ingest import list_ingest_pipelines
print(list_ingest_pipelines())
```

## Desktop app

The packaged app does not freeze optional plugins into `vera-sidecar.exe`.
Configure a trusted external Python interpreter under **File > LLM Providers**,
install the plugin into that environment, then Validate / Refresh. Convert
lists bundled pipelines from the sidecar and extra providers from the plugin
host. Duplicate provider names keep the bundled implementation.

See [Run the desktop app](desktop-app-getting-started.md) and
[Desktop app architecture](desktop-app-architecture.md).
