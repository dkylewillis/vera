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
    IngestRequest,
    IngestResult,
    ParsedPage,
    PipelineDescriptor,
    PipelineField,
    UnknownIngestPipelineError,
    batch_convert,
    convert,
    describe_ingest_pipeline,
    get_chunk_regions,
    get_ingest_pipeline,
    list_ingest_pipeline_descriptors,
    list_ingest_pipelines,
    prepare_pipeline_options,
    register_ingest_pipeline,
    register_ingest_pipeline_descriptor,
    reset_ingest_pipeline_registry,
)
from vera_ingest_pymupdf.options import PyMuPDFOptions


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


def test_register_ingest_pipeline_works_as_a_decorator():
    class Pipeline:
        def ingest(self, source_path, options):
            raise AssertionError("not called")

    @register_ingest_pipeline("decorated")
    def create_pipeline(variant: str = "") -> Pipeline:
        return Pipeline()

    # The decorator returns the wrapped factory unchanged.
    assert create_pipeline("") is not None
    assert isinstance(get_ingest_pipeline("decorated"), Pipeline)

    @register_ingest_pipeline_descriptor("decorated")
    def create_descriptor(variant: str = "") -> PipelineDescriptor:
        return PipelineDescriptor(
            provider="decorated", variant="", spec="decorated", label="decorated"
        )

    assert describe_ingest_pipeline("decorated").label == "decorated"


def test_bare_callable_pipeline_is_supported(tmp_path):
    """A pipeline may be a plain function; ``.ingest()`` is not required."""
    pdf = tmp_path / "source.pdf"
    out = tmp_path / "source.vera"
    pdf.write_bytes(b"%PDF bare-callable pipeline test")

    def bare_pipeline(source_path: str, options: IngestRequest) -> IngestResult:
        assert source_path == str(pdf)
        return IngestResult(
            pages=[ParsedPage(1, 1.0, 1.0, "text")],
            blocks=[
                IngestBlock(block_id="b1", page_number=1, block_type="paragraph", text="text")
            ],
            chunks=[
                IngestChunk(
                    chunk_id="c1",
                    text="text",
                    page_start=1,
                    page_end=1,
                    heading_path="",
                    token_count=1,
                    block_ids=["b1"],
                )
            ],
            parser_name="bare",
            parser_version="1",
            chunking_strategy="bare",
        )

    register_ingest_pipeline("bare", lambda _variant: bare_pipeline)
    assert get_ingest_pipeline("bare") is bare_pipeline

    convert(str(pdf), str(out), parser="bare", store_original=False)
    with VeraDocument.open(str(out)) as document:
        assert document.inspect()["parser_name"] == "bare"


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

    def fake_entry_points(**kwargs):
        group = kwargs.get("group")
        if group == "vera.ingest_pipelines":
            return [EntryPoint()]
        return []

    monkeypatch.setattr(pipeline_module, "entry_points", fake_entry_points)

    assert loaded == []
    assert "example" in list_ingest_pipelines()
    assert loaded == [True]
    assert isinstance(get_ingest_pipeline("example"), Pipeline)


def test_unknown_pipeline_is_strict_and_does_not_parse(tmp_path, monkeypatch):
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"not parsed")
    parser_module = importlib.import_module("vera_ingest_pymupdf.parser")

    def boom(*args, **kwargs):
        raise AssertionError("parsing must not run")

    monkeypatch.setattr(parser_module, "parse_pdf_structured", boom)
    with pytest.raises(UnknownIngestPipelineError, match="vera-ingest-pymupdf"):
        convert(str(pdf), str(tmp_path / "out.vera"), parser="missing")


def test_batch_rejects_unknown_pipeline_before_discovery(tmp_path):
    with pytest.raises(UnknownIngestPipelineError, match="vera-ingest-pymupdf"):
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


def test_pymupdf_descriptor_and_strict_options():
    descriptor = describe_ingest_pipeline("pymupdf")
    assert descriptor.spec == "pymupdf"
    assert {field.key for field in descriptor.fields} == {
        "chunk_size",
        "overlap",
        "ocr_mode",
        "ocr_language",
        "ocr_dpi",
        "ocr_download",
    }
    assert descriptor.as_dict()["capabilities"]["ocr_engine"] == "tesseract"
    ocr_language = next(field for field in descriptor.fields if field.key == "ocr_language")
    assert ocr_language.type == "enum"
    assert ocr_language.allow_custom is True
    choice_values = [choice.value for choice in ocr_language.choices]
    assert choice_values[0] == "eng"
    assert "spa" in choice_values
    assert "fra" in choice_values
    assert any(choice.label == "Spanish (spa)" for choice in ocr_language.choices)
    options = PyMuPDFOptions.from_mapping({"chunk_size": 250, "overlap": 10})
    assert options.chunk_size == 250
    assert options.overlap == 10
    assert options.ocr_mode == "auto"
    # Combinations and unknown codes remain valid strings for CLI / custom installs.
    assert PyMuPDFOptions.from_mapping({"ocr_language": "eng+spa"}).ocr_language == "eng+spa"
    with pytest.raises(ValueError, match="Unknown PyMuPDF option"):
        PyMuPDFOptions.from_mapping({"chunk_size": 250, "bogus": 1})
    with pytest.raises(ValueError, match="chunk_size must be positive"):
        PyMuPDFOptions.from_mapping({"chunk_size": 0})


def test_fields_from_dataclass_derives_descriptor_fields_from_metadata():
    from dataclasses import dataclass, field

    from vera_ingest.descriptors import fields_from_dataclass

    @dataclass(frozen=True)
    class Options:
        chunk_size: int = field(
            default=250, metadata={"label": "Chunk size", "minimum": 10}
        )
        ocr_mode: str = field(
            default="auto", metadata={"type": "enum", "choices": (("auto", "Auto"),)}
        )
        internal: str = "not advertised"  # no metadata: omitted from the descriptor

    fields = fields_from_dataclass(Options)

    assert [item.key for item in fields] == ["chunk_size", "ocr_mode"]
    chunk_size_field = fields[0]
    assert chunk_size_field.label == "Chunk size"
    assert chunk_size_field.type == "integer"  # inferred from the `int` annotation
    assert chunk_size_field.default == 250
    assert chunk_size_field.minimum == 10
    ocr_mode_field = fields[1]
    assert ocr_mode_field.type == "enum"  # explicit override
    assert [choice.value for choice in ocr_mode_field.choices] == ["auto"]


def test_descriptor_fallback_for_undescribed_plugins():
    register_ingest_pipeline("opaque", lambda _variant: object())
    descriptor = describe_ingest_pipeline("opaque")
    assert isinstance(descriptor, PipelineDescriptor)
    assert descriptor.fields == ()
    assert "did not publish" in descriptor.notes[0]
    specs = [item.spec for item in list_ingest_pipeline_descriptors()]
    assert "opaque" in specs
    assert "pymupdf" in specs


def test_prepare_pipeline_options_respects_descriptor_and_explicit_overrides():
    merged = prepare_pipeline_options(
        spec="pymupdf",
        legacy_options={
            "chunk_size": 400,
            "overlap": 50,
            "ocr_mode": "force",
            "ocr_language": "eng",
            "ocr_dpi": 200,
        },
        pipeline_options={"chunk_size": 900, "ocr_language": "deu"},
    )
    assert merged == {
        "chunk_size": 900,
        "overlap": 50,
        "ocr_mode": "force",
        "ocr_language": "deu",
        "ocr_dpi": 200,
    }


def test_convert_forwards_thin_request_and_isolates_legacy_keys(tmp_path):
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"%PDF isolated")

    class Capturing:
        def __init__(self):
            self.request = None

        def ingest(self, source_path, options):
            self.request = options
            return IngestResult(
                pages=[ParsedPage(1, 1.0, 1.0, "readable")],
                blocks=[
                    IngestBlock(
                        block_id="b1",
                        page_number=1,
                        block_type="paragraph",
                        text="readable",
                    )
                ],
                chunks=[
                    IngestChunk(
                        chunk_id="c1",
                        text="readable",
                        page_start=1,
                        page_end=1,
                        heading_path="",
                        token_count=1,
                        block_ids=["b1"],
                    )
                ],
                parser_name="capture",
                parser_version="1",
                chunking_strategy="capture",
            )

    undescribed = Capturing()
    described = Capturing()
    register_ingest_pipeline("undescribed", lambda _variant: undescribed)
    register_ingest_pipeline("described", lambda _variant: described)
    register_ingest_pipeline_descriptor(
        "described",
        lambda _variant: PipelineDescriptor(
            provider="described",
            variant="",
            spec="described",
            label="described",
            fields=(
                PipelineField(
                    key="chunk_size",
                    label="Chunk size",
                    type="integer",
                    default=500,
                ),
            ),
        ),
    )

    class Embedder:
        model_name = "isolation-test"
        dimension = 2
        normalization = "l2"

        def embed(self, texts):
            return np.asarray([[1.0, 0.0] for _ in texts], dtype=np.float32)

    convert(
        str(pdf),
        str(tmp_path / "u.vera"),
        parser="undescribed",
        embedding_function=Embedder(),
        overlap=33,
        ocr_dpi=222,
        store_original=False,
    )
    convert(
        str(pdf),
        str(tmp_path / "d.vera"),
        parser="described",
        embedding_function=Embedder(),
        overlap=33,
        ocr_dpi=222,
        chunk_size=321,
        pipeline_options={"chunk_size": 654},
        store_original=False,
    )

    assert isinstance(undescribed.request, IngestRequest)
    assert undescribed.request.pipeline_options["overlap"] == 33
    assert undescribed.request.pipeline_options["ocr_dpi"] == 222
    assert isinstance(described.request, IngestRequest)
    assert described.request.pipeline_options == {"chunk_size": 654}
    assert "overlap" not in described.request.pipeline_options
    assert "ocr_dpi" not in described.request.pipeline_options


def test_ingest_options_to_request_preserves_explicit_pipeline_options():
    request = IngestOptions(
        chunk_size=100,
        overlap=1,
        pipeline_options={"chunk_size": 777, "custom": True},
    ).to_request()
    assert request.pipeline_options["chunk_size"] == 777
    assert request.pipeline_options["custom"] is True
    assert request.pipeline_options["overlap"] == 1


def test_descriptor_entry_points_are_discovered_lazily(monkeypatch):
    pipeline_module = importlib.import_module("vera_ingest.pipeline")

    class Pipeline:
        def ingest(self, source_path, options):
            raise AssertionError("not called")

    class PipelineEntry:
        name = "hinted"

        def load(self):
            return lambda variant: Pipeline()

    class DescriptorEntry:
        name = "hinted"

        def load(self):
            return lambda variant: PipelineDescriptor(
                provider="hinted",
                variant="",
                spec="hinted",
                label="hinted",
                fields=(),
            )

    reset_ingest_pipeline_registry()

    def fake_entry_points(**kwargs):
        group = kwargs.get("group")
        if group == "vera.ingest_pipelines":
            return [PipelineEntry()]
        if group == "vera.ingest_pipeline_descriptors":
            return [DescriptorEntry()]
        return []

    monkeypatch.setattr(pipeline_module, "entry_points", fake_entry_points)
    descriptor = describe_ingest_pipeline("hinted")
    assert descriptor.spec == "hinted"
    assert descriptor.label == "hinted"

