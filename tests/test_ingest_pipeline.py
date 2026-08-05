import importlib
import json
import sqlite3
from importlib.metadata import version

import numpy as np
import pytest
from vera import VeraDocument
from vera_ingest import (
    IngestBlock,
    IngestChunk,
    IngestOptions,
    IngestResult,
    ParsedPage,
    UnknownIngestPipelineError,
    batch_convert,
    convert,
    get_chunk_regions,
    get_ingest_pipeline,
    list_ingest_pipelines,
    register_ingest_pipeline,
    reset_ingest_pipeline_registry,
)


@pytest.fixture(autouse=True)
def isolated_pipeline_registry():
    reset_ingest_pipeline_registry()
    yield
    reset_ingest_pipeline_registry()


def test_builtin_pipeline_is_cached_and_listed():
    first = get_ingest_pipeline("pymupdf")
    second = get_ingest_pipeline("PYMUPDF")

    assert first is second
    assert "pymupdf" in list_ingest_pipelines()


def test_builtin_conversion_records_real_pymupdf_version(tmp_path):
    import fitz

    pdf = tmp_path / "source.pdf"
    out = tmp_path / "source.vera"
    source = fitz.open()
    page = source.new_page()
    page.insert_text((72, 72), "Searchable built-in pipeline text.")
    source.save(pdf)
    source.close()

    convert(str(pdf), str(out), store_original=False)

    with VeraDocument.open(str(out)) as document:
        assert document.inspect()["parser_version"] == version("PyMuPDF")


def test_registry_forwards_variants_and_docling_defaults_to_hybrid():
    variants = []

    class Pipeline:
        def ingest(self, source_path, options):
            raise AssertionError("not called")

    def factory(variant):
        variants.append(variant)
        return Pipeline()

    register_ingest_pipeline("docling", factory)

    assert get_ingest_pipeline("docling") is get_ingest_pipeline("docling:hybrid")
    assert variants == ["hybrid"]


def test_duplicate_registration_is_rejected():
    register_ingest_pipeline("custom", lambda _variant: object())

    with pytest.raises(ValueError, match="already registered"):
        register_ingest_pipeline("custom", lambda _variant: object())


def test_entry_points_are_discovered_lazily(monkeypatch):
    pipeline_module = importlib.import_module("vera_ingest.pipeline")
    loaded = []

    class Pipeline:
        def ingest(self, source_path, options):
            raise AssertionError("not called")

    class EntryPoint:
        name = "example"

        def load(self):
            loaded.append(True)
            return lambda variant: Pipeline()

    reset_ingest_pipeline_registry()
    monkeypatch.setattr(
        pipeline_module,
        "entry_points",
        lambda **kwargs: [EntryPoint()],
    )

    assert loaded == []
    assert "example" in list_ingest_pipelines()
    assert loaded == [True]
    assert isinstance(get_ingest_pipeline("example"), Pipeline)


def test_unknown_pipeline_is_strict_and_does_not_parse(tmp_path, monkeypatch):
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"not parsed")
    convert_module = importlib.import_module("vera_ingest.convert")

    def boom(*args, **kwargs):
        raise AssertionError("parsing must not run")

    monkeypatch.setattr(convert_module, "parse_pdf_structured", boom)
    with pytest.raises(UnknownIngestPipelineError, match="Install a plugin"):
        convert(str(pdf), str(tmp_path / "out.vera"), parser="missing")


def test_batch_rejects_unknown_pipeline_before_discovery(tmp_path):
    with pytest.raises(UnknownIngestPipelineError, match="Install a plugin"):
        batch_convert(str(tmp_path / "missing"), parser="missing")


def test_custom_pipeline_keeps_readable_text_and_embeds_context(tmp_path):
    pdf = tmp_path / "source.pdf"
    out = tmp_path / "source.vera"
    pdf.write_bytes(b"%PDF fake source retained as an attachment")

    class Pipeline:
        def ingest(self, source_path: str, options: IngestOptions) -> IngestResult:
            assert source_path == str(pdf)
            assert options.variant == "special"
            return IngestResult(
                pages=[
                    ParsedPage(1, 612.0, 792.0, "Readable text"),
                    ParsedPage(2, 612.0, 792.0, "Continued text"),
                ],
                blocks=[
                    IngestBlock(
                        block_id="stable-block",
                        page_number=1,
                        block_type="paragraph",
                        text="Readable text",
                        bbox=(10.0, 20.0, 100.0, 40.0),
                        regions=[
                            {"page_number": 1, "bbox": (10.0, 20.0, 100.0, 40.0)},
                            {"page_number": 2, "bbox": (10.0, 30.0, 100.0, 50.0)},
                        ],
                    )
                ],
                chunks=[
                    IngestChunk(
                        chunk_id="stable-chunk",
                        text="Readable text",
                        embedding_text="Heading context: Readable text",
                        page_start=1,
                        page_end=2,
                        heading_path="Heading context",
                        token_count=2,
                        block_ids=["stable-block"],
                    )
                ],
                parser_name="example",
                parser_version="1.2.3",
                chunking_strategy="example-native",
                diagnostics={"mode": "fixture"},
            )

    class RecordingEmbedder:
        model_name = "recording"
        dimension = 2
        normalization = "l2"

        def __init__(self):
            self.calls = []

        def embed(self, texts):
            self.calls.append(list(texts))
            return np.asarray([[1.0, 0.0] for _ in texts], dtype=np.float32)

    register_ingest_pipeline("example", lambda variant: Pipeline())
    embedder = RecordingEmbedder()
    convert(
        str(pdf),
        str(out),
        parser="example:special",
        embedding_function=embedder,
    )

    assert embedder.calls == [["Heading context: Readable text"]]
    with VeraDocument.open(str(out), embedding_function=embedder) as document:
        info = document.inspect()
        assert info["parser_name"] == "example"
        assert info["chunking_strategy"] == "example-native"
        result = document.search("Readable", mode="keyword", top_k=1)[0]
        assert result.chunk_id == "stable-chunk"
        assert result.text == "Readable text"
        regions = get_chunk_regions(document, result.chunk_id)
        assert regions[0]["block_id"] == "stable-block"
        assert [region["page_number"] for region in regions] == [1, 2]
    with sqlite3.connect(out) as connection:
        metadata = json.loads(connection.execute(
            "SELECT value FROM vera_metadata WHERE key='archive_metadata'"
        ).fetchone()[0])
        assert metadata["parser_version"] == "1.2.3"


def test_pipeline_result_rejects_unknown_block_references(tmp_path):
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"source")

    class Pipeline:
        def ingest(self, source_path, options):
            return IngestResult(
                pages=[ParsedPage(1, 1.0, 1.0, "text")],
                blocks=[],
                chunks=[
                    IngestChunk(
                        chunk_id="chunk",
                        text="text",
                        page_start=1,
                        page_end=1,
                        heading_path="",
                        token_count=1,
                        block_ids=["missing"],
                    )
                ],
                parser_name="broken",
                parser_version="1",
                chunking_strategy="broken",
            )

    register_ingest_pipeline("broken", lambda variant: Pipeline())
    with pytest.raises(ValueError, match="unknown block IDs"):
        convert(
            str(pdf),
            str(tmp_path / "out.vera"),
            parser="broken",
            embedding_function=type(
                "Embedder",
                (),
                {
                    "model_name": "unused",
                    "dimension": 1,
                    "normalization": "l2",
                    "embed": lambda self, texts: np.ones((len(texts), 1)),
                },
            )(),
        )

