"""Build plugin wheels from tests/support without a build backend or network."""

from __future__ import annotations

import zipfile
from pathlib import Path

ECHO_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "support"
    / "echo_ingest_plugin"
    / "src"
    / "echo_ingest_plugin"
)

ECHO_ENTRY_POINTS = """\
[vera.ingest_pipelines]
echo = echo_ingest_plugin:create_pipeline

[vera.ingest_pipeline_descriptors]
echo = echo_ingest_plugin:create_descriptor
"""


NOTES_PIPELINE = """
import time
from pathlib import Path

from vera_ingest.descriptors import PipelineCapabilities, PipelineDescriptor
from vera_ingest.types import IngestBlock, IngestChunk, IngestResult, ParsedPage


def create_pipeline(variant=""):
    def ingest(source_path, request):
        text = Path(source_path).read_text(encoding="utf-8")
        if text.startswith("FAIL"):
            raise ValueError("the notes pipeline refused this file")
        if text.startswith("SLOW"):
            heartbeat = Path(source_path + ".heartbeat")
            for beat in range(600):
                heartbeat.write_text(str(beat), encoding="utf-8")
                time.sleep(0.1)
        mark = (request.pipeline_options or {}).get("mark", "")
        return IngestResult(
            pages=[ParsedPage(page_number=1, width=612, height=792, text=text)],
            blocks=[IngestBlock(block_id="b1", page_number=1, block_type="paragraph", text=text)],
            chunks=[
                IngestChunk(
                    chunk_id="c1",
                    text=text,
                    page_start=1,
                    page_end=1,
                    heading_path="",
                    token_count=len(text.split()),
                    block_ids=["b1"],
                )
            ],
            parser_name="notes",
            parser_version="0.0.1",
            chunking_strategy=f"whole:{mark}",
        )

    return ingest


def create_descriptor(variant=""):
    return PipelineDescriptor(
        provider="notes",
        variant="",
        spec="notes",
        label="notes (separate environment test)",
        capabilities=PipelineCapabilities(source_formats=("note",)),
    )
"""

NOTES_ENTRY_POINTS = """\
[vera.ingest_pipelines]
notes = notes_pipeline:create_pipeline

[vera.ingest_pipeline_descriptors]
notes = notes_pipeline:create_descriptor
"""


def write_notes_environment(folder: Path) -> Path:
    """Write an installed ``notes`` pipeline (reads ``.note`` files) into ``folder``.

    Put ``folder`` on a child interpreter's ``PYTHONPATH`` to make that child a
    separate environment: it has the pipeline and the test process does not.
    A file starting with ``FAIL`` raises; one starting with ``SLOW`` writes a
    ``<file>.heartbeat`` counter for a minute before finishing.
    """
    package = folder / "notes_pipeline"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(NOTES_PIPELINE, encoding="utf-8")
    dist_info = folder / "notes_pipeline-0.0.1.dist-info"
    dist_info.mkdir()
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: notes-pipeline\nVersion: 0.0.1\n", encoding="utf-8"
    )
    (dist_info / "entry_points.txt").write_text(NOTES_ENTRY_POINTS, encoding="utf-8")
    return folder


def make_echo_wheel(
    directory: Path,
    *,
    version: str = "0.0.1",
    tag: str = "py3-none-any",
    entry_points: str = ECHO_ENTRY_POINTS,
    requires: tuple[str, ...] = ("vera-ingest",),
) -> Path:
    """Write ``echo_ingest_plugin-<version>-<tag>.whl`` (the echo test pipeline)."""
    dist_info = f"echo_ingest_plugin-{version}.dist-info"
    wheel = directory / f"echo_ingest_plugin-{version}-{tag}.whl"
    metadata = "\n".join(
        [
            "Metadata-Version: 2.1",
            "Name: echo-ingest-plugin",
            f"Version: {version}",
            "Summary: Test ingest pipeline used by VERA plugin-host tests",
            *(f"Requires-Dist: {requirement}" for requirement in requires),
            "",
        ]
    )
    purelib = "true" if tag.endswith("-none-any") else "false"
    wheel_file = (
        f"Wheel-Version: 1.0\nGenerator: vera-tests\nRoot-Is-Purelib: {purelib}\nTag: {tag}\n"
    )
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.write(ECHO_SOURCE / "__init__.py", "echo_ingest_plugin/__init__.py")
        archive.writestr(f"{dist_info}/METADATA", metadata)
        archive.writestr(f"{dist_info}/WHEEL", wheel_file)
        archive.writestr(f"{dist_info}/entry_points.txt", entry_points)
        archive.writestr(f"{dist_info}/RECORD", "")
    return wheel
