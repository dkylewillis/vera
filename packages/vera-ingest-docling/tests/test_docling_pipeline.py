"""Offline Docling ingest pipeline tests (no model/network downloads)."""

from __future__ import annotations

import io
import os

import numpy as np
import pytest

pytest.importorskip("docling")
pytest.importorskip("docling_core")

from docling.datamodel.base_models import ConversionStatus, DoclingComponentType, ErrorItem
from docling_core.types.doc import (
    DocItemLabel,
    DoclingDocument,
    PictureItem,
    ProvenanceItem,
    RefItem,
)
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from PIL import Image

from vera_doc import VeraDocument
from vera_ingest import (
    UnknownIngestPipelineError,
    convert,
    get_ingest_pipeline,
    list_ingest_pipelines,
    reset_ingest_pipeline_registry,
)
from vera_ingest.types import IngestChunk, IngestOptions, IngestRequest
from vera_ingest_docling import create_pipeline
from vera_ingest_docling.mapping import _chunk_document, _item_text
from vera_ingest_docling.pipeline import (
    DoclingHybridPipeline,
    WhitespaceTokenizer,
    _split_ocr_languages,
    map_docling_document,
)

pytestmark = pytest.mark.docling


def _write_complete_docling_artifacts(root) -> None:
    from pathlib import Path

    artifacts = Path(root)
    heron = artifacts / "docling-project--docling-layout-heron-onnx"
    heron.mkdir(parents=True, exist_ok=True)
    (heron / "config.json").write_text("{}", encoding="utf-8")
    (heron / "model.onnx").write_bytes(b"weights")
    table = (
        artifacts
        / "docling-project--docling-models"
        / "model_artifacts"
        / "tableformer"
        / "accurate"
    )
    table.mkdir(parents=True, exist_ok=True)
    (table / "tm_config.json").write_text("{}", encoding="utf-8")


@pytest.fixture(autouse=True)
def isolated_registry():
    reset_ingest_pipeline_registry()
    yield
    reset_ingest_pipeline_registry()


@pytest.fixture(autouse=True)
def skip_docling_model_download(monkeypatch):
    monkeypatch.setattr(
        "vera_ingest_docling.converter._download_docling_models",
        lambda artifacts: artifacts,
    )


def _prov(
    page_no: int, l: float, b: float, r: float, t: float, height: float = 792.0
) -> ProvenanceItem:
    return ProvenanceItem(
        page_no=page_no,
        bbox=BoundingBox(l=l, t=t, r=r, b=b, coord_origin=CoordOrigin.BOTTOMLEFT),
        charspan=(0, 1),
    )


def _fixture_document() -> DoclingDocument:
    doc = DoclingDocument(name="fixture")
    doc.add_page(page_no=1, size=Size(width=612.0, height=792.0))
    doc.add_page(page_no=2, size=Size(width=612.0, height=792.0))
    doc.add_heading(
        text="Chapter 1",
        level=1,
        prov=_prov(1, 72, 700, 300, 720),
    )
    doc.add_text(
        label=DocItemLabel.PARAGRAPH,
        text="First page paragraph about detention ponds.",
        prov=_prov(1, 72, 640, 500, 680),
    )
    doc.add_text(
        label=DocItemLabel.PARAGRAPH,
        text="Second page continues the requirements.",
        prov=_prov(2, 72, 640, 500, 680),
    )
    table_data = [
        ["Pipe", "Size"],
        ["A", "12"],
    ]
    try:
        from docling_core.types.doc import TableCell, TableData

        data = TableData(num_rows=2, num_cols=2)
        for row_idx, row in enumerate(table_data):
            for col_idx, text in enumerate(row):
                data.table_cells.append(
                    TableCell(
                        text=text,
                        row_span=1,
                        col_span=1,
                        start_row_offset_idx=row_idx,
                        end_row_offset_idx=row_idx + 1,
                        start_col_offset_idx=col_idx,
                        end_col_offset_idx=col_idx + 1,
                        column_header=row_idx == 0,
                    )
                )
        doc.add_table(data=data, prov=_prov(1, 72, 400, 300, 500))
    except Exception:
        # Older/newer Docling table constructors vary; paragraph fallback keeps mapping tests useful.
        doc.add_text(
            label=DocItemLabel.PARAGRAPH,
            text="Pipe | Size\nA | 12",
            prov=_prov(1, 72, 400, 300, 500),
        )

    image = Image.new("RGB", (32, 32), color=(20, 40, 60))
    try:
        from docling_core.types.doc import ImageRef

        doc.add_picture(
            prov=_prov(1, 350, 400, 500, 500),
            image=ImageRef.from_pil(image=image, dpi=72),
        )
    except Exception:
        picture = doc.add_picture(prov=_prov(1, 350, 400, 500, 500))
        if hasattr(picture, "image"):
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")

    doc.add_text(
        label=DocItemLabel.CAPTION,
        text="Figure 1: Example figure caption.",
        prov=_prov(1, 350, 380, 520, 395),
    )
    return doc


def test_factory_accepts_hybrid_and_rejects_unknown_variants():
    assert isinstance(create_pipeline("hybrid"), DoclingHybridPipeline)
    assert isinstance(create_pipeline(""), DoclingHybridPipeline)
    with pytest.raises(UnknownIngestPipelineError, match="docling:hybrid"):
        create_pipeline("legacy")


def test_entry_point_registers_docling_provider():
    assert "docling" in list_ingest_pipelines()
    assert get_ingest_pipeline("docling") is get_ingest_pipeline("docling:hybrid")


def test_map_docling_document_converts_coords_and_types():
    document = _fixture_document()
    pages, blocks = map_docling_document(document)

    assert [page.page_number for page in pages] == [1, 2]
    assert pages[0].height == 792.0
    headings = [block for block in blocks if block.block_type == "heading"]
    paragraphs = [block for block in blocks if block.block_type == "paragraph"]
    captions = [block for block in blocks if block.block_type == "caption"]
    images = [block for block in blocks if block.block_type == "image"]
    assert headings
    assert paragraphs
    assert captions
    assert headings[0].heading_level == 1
    assert (
        headings[0].block_id.startswith("texts_")
        or "heading" in headings[0].block_id
        or headings[0].block_id
    )
    # Bottom-left (72,700)-(300,720) on 792-tall page -> top-left y = 72 and 92.
    assert headings[0].bbox is not None
    left, top, right, bottom = headings[0].bbox
    assert left == pytest.approx(72.0)
    assert right == pytest.approx(300.0)
    assert top == pytest.approx(72.0)
    assert bottom == pytest.approx(92.0)
    assert any("detention ponds" in block.text for block in paragraphs)
    assert any("Figure 1" in block.text for block in captions)
    assert images
    assert images[0].image_bytes
    assert images[0].image_ext == "png"


def test_whitespace_tokenizer_is_deterministic():
    tokenizer = WhitespaceTokenizer(max_tokens=12)
    assert tokenizer.count_tokens("one two three") == 3
    assert tokenizer.get_max_tokens() == 12
    assert tokenizer.get_tokenizer()("a b") == 2


def test_split_ocr_languages_parses_delimited_codes_without_translation():
    """No Tesseract-to-RapidOCR mapping happens anymore — codes pass through as given."""
    assert _split_ocr_languages(None) == ["en"]
    assert _split_ocr_languages("") == ["en"]
    assert _split_ocr_languages("en") == ["en"]
    assert _split_ocr_languages("en+fr") == ["en", "fr"]
    assert _split_ocr_languages("en,de") == ["en", "de"]
    # No validation against a known set: an unrecognized code passes through
    # unchanged. RapidOCR itself rejects it once OCR actually runs.
    assert _split_ocr_languages("eng") == ["eng"]


def test_build_converter_uses_ocr_language_as_given_no_translation():
    from pathlib import Path

    from vera_ingest_docling.options import DoclingOptions
    from vera_ingest_docling.pipeline import _build_converter

    converter = _build_converter(
        DoclingOptions.from_mapping({"ocr_mode": "auto", "ocr_language": "en+fr"}),
    )
    pdf_option = converter.format_to_options["pdf"]
    assert pdf_option.pipeline_options.do_ocr is True
    assert list(pdf_option.pipeline_options.ocr_options.lang) == ["en", "fr"]
    ocr_options = pdf_option.pipeline_options.ocr_options
    assert Path(ocr_options.det_model_path).is_file()
    assert Path(ocr_options.cls_model_path).is_file()
    assert Path(ocr_options.rec_model_path).is_file()
    assert "rapidocr" in Path(ocr_options.det_model_path).as_posix().lower()


def test_empty_artifacts_path_allows_hub_download(monkeypatch, tmp_path):
    from docling.datamodel.settings import settings

    from vera_ingest_docling.converter import _configure_docling_artifacts

    monkeypatch.setattr(settings, "artifacts_path", settings.artifacts_path)
    monkeypatch.setenv("DOCLING_ARTIFACTS_PATH", str(tmp_path))
    monkeypatch.delenv("HF_HOME", raising=False)
    settings.artifacts_path = tmp_path
    _configure_docling_artifacts()
    assert settings.artifacts_path is None
    assert os.environ.get("HF_HOME") == str(tmp_path)


def test_config_only_layout_folder_stays_online(monkeypatch, tmp_path):
    from docling.datamodel.settings import settings

    from vera_ingest_docling.converter import _configure_docling_artifacts

    monkeypatch.setattr(settings, "artifacts_path", settings.artifacts_path)
    heron = tmp_path / "docling-project--docling-layout-heron-onnx"
    heron.mkdir()
    (heron / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("DOCLING_ARTIFACTS_PATH", str(tmp_path))
    settings.artifacts_path = tmp_path
    _configure_docling_artifacts()
    assert settings.artifacts_path is None


def test_layout_without_tableformer_stays_online(monkeypatch, tmp_path):
    from docling.datamodel.settings import settings

    from vera_ingest_docling.converter import _configure_docling_artifacts

    monkeypatch.setattr(settings, "artifacts_path", settings.artifacts_path)
    heron = tmp_path / "docling-project--docling-layout-heron-onnx"
    heron.mkdir()
    (heron / "config.json").write_text("{}", encoding="utf-8")
    (heron / "model.onnx").write_bytes(b"weights")
    monkeypatch.setenv("DOCLING_ARTIFACTS_PATH", str(tmp_path))
    settings.artifacts_path = tmp_path
    _configure_docling_artifacts()
    assert settings.artifacts_path is None


def test_populated_artifacts_path_stays_offline(monkeypatch, tmp_path):
    from pathlib import Path

    from docling.datamodel.settings import settings

    from vera_ingest_docling.converter import _configure_docling_artifacts

    monkeypatch.setattr(settings, "artifacts_path", settings.artifacts_path)
    _write_complete_docling_artifacts(tmp_path)
    monkeypatch.setenv("DOCLING_ARTIFACTS_PATH", str(tmp_path))
    _configure_docling_artifacts()
    assert Path(settings.artifacts_path) == tmp_path


def test_populated_artifacts_path_preserves_existing_hf_home(monkeypatch, tmp_path):
    from pathlib import Path

    from docling.datamodel.settings import settings

    from vera_ingest_docling.converter import _configure_docling_artifacts

    monkeypatch.setattr(settings, "artifacts_path", settings.artifacts_path)
    _write_complete_docling_artifacts(tmp_path)
    hub = tmp_path / "writable-hub"
    hub.mkdir()
    monkeypatch.setenv("DOCLING_ARTIFACTS_PATH", str(tmp_path))
    monkeypatch.setenv("HF_HOME", str(hub))
    _configure_docling_artifacts()
    assert Path(settings.artifacts_path) == tmp_path
    assert os.environ["HF_HOME"] == str(hub)


def test_configure_docling_artifacts_tolerates_mkdir_failure_when_cache_exists(
    monkeypatch, tmp_path
):
    from pathlib import Path

    from docling.datamodel.settings import settings

    from vera_ingest_docling.converter import _configure_docling_artifacts

    monkeypatch.setattr(settings, "artifacts_path", settings.artifacts_path)
    _write_complete_docling_artifacts(tmp_path)
    monkeypatch.setenv("DOCLING_ARTIFACTS_PATH", str(tmp_path))

    def fail_mkdir(self, *args, **kwargs):
        raise PermissionError("read-only filesystem")

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)
    _configure_docling_artifacts()
    assert Path(settings.artifacts_path) == tmp_path


def test_configure_docling_artifacts_reraises_mkdir_failure_when_cache_missing(
    monkeypatch, tmp_path
):
    from pathlib import Path

    from vera_ingest_docling.converter import _configure_docling_artifacts

    missing = tmp_path / "missing-cache"
    monkeypatch.setenv("DOCLING_ARTIFACTS_PATH", str(missing))

    def fail_mkdir(self, *args, **kwargs):
        raise PermissionError("read-only filesystem")

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)
    with pytest.raises(PermissionError, match="read-only"):
        _configure_docling_artifacts()


def test_ensure_docling_models_downloads_when_cache_incomplete(monkeypatch, tmp_path):
    from docling.datamodel.settings import settings

    from vera_ingest_docling import converter as converter_mod

    monkeypatch.setattr(settings, "artifacts_path", settings.artifacts_path)
    seen = {}

    def fake_download(artifacts):
        seen["path"] = artifacts
        _write_complete_docling_artifacts(artifacts)

    monkeypatch.setattr(converter_mod, "_download_docling_models", fake_download)
    monkeypatch.setenv("DOCLING_ARTIFACTS_PATH", str(tmp_path))
    monkeypatch.delenv("HF_HOME", raising=False)
    result = converter_mod.ensure_docling_models()
    assert seen["path"] == tmp_path
    assert result["ready"] is True
    assert result["downloaded"] is True
    assert result["artifacts_path"] == str(tmp_path)


def test_ensure_docling_models_skips_download_when_cache_ready(monkeypatch, tmp_path):
    from docling.datamodel.settings import settings

    from vera_ingest_docling import converter as converter_mod

    monkeypatch.setattr(settings, "artifacts_path", settings.artifacts_path)

    def fail_download(artifacts):
        raise AssertionError("complete cache must not download")

    _write_complete_docling_artifacts(tmp_path)
    monkeypatch.setattr(converter_mod, "_download_docling_models", fail_download)
    monkeypatch.setenv("DOCLING_ARTIFACTS_PATH", str(tmp_path))
    result = converter_mod.ensure_docling_models()
    assert result == {
        "ready": True,
        "downloaded": False,
        "artifacts_path": str(tmp_path),
    }


def test_build_converter_prefers_artifacts_rapidocr_when_complete(monkeypatch, tmp_path):
    from pathlib import Path

    from vera_ingest_docling.converter import _RAPIDOCR_MODEL_FILES, _build_converter
    from vera_ingest_docling.options import DoclingOptions

    cache = tmp_path / "RapidOcr"
    cache.mkdir()
    for name in _RAPIDOCR_MODEL_FILES.values():
        (cache / name).write_bytes(b"onnx")
    monkeypatch.setenv("DOCLING_ARTIFACTS_PATH", str(tmp_path))
    converter = _build_converter(DoclingOptions.from_mapping({"ocr_mode": "auto"}))
    ocr_options = converter.format_to_options["pdf"].pipeline_options.ocr_options
    assert Path(ocr_options.det_model_path) == cache / "PP-OCRv6_det_small.onnx"


def test_build_converter_uses_packaged_rapidocr_when_artifacts_incomplete(monkeypatch, tmp_path):
    from pathlib import Path

    from vera_ingest_docling.converter import _build_converter
    from vera_ingest_docling.options import DoclingOptions

    (tmp_path / "RapidOcr").mkdir()
    monkeypatch.setenv("DOCLING_ARTIFACTS_PATH", str(tmp_path))
    converter = _build_converter(DoclingOptions.from_mapping({"ocr_mode": "auto"}))
    ocr_options = converter.format_to_options["pdf"].pipeline_options.ocr_options
    assert Path(ocr_options.det_model_path).is_file()
    assert "rapidocr" in Path(ocr_options.det_model_path).as_posix().lower()


def test_build_converter_uses_onnx_layout_and_accurate_tableformer():
    from vera_ingest_docling.options import DoclingOptions
    from vera_ingest_docling.pipeline import _build_converter

    converter = _build_converter(
        DoclingOptions.from_mapping({"ocr_mode": "auto", "ocr_language": "en"}),
    )
    pipeline_options = converter.format_to_options["pdf"].pipeline_options
    assert pipeline_options.images_scale == 1.0
    assert pipeline_options.generate_picture_images is True
    engine = pipeline_options.layout_options.engine_options
    assert engine.engine_type.value == "onnxruntime"
    assert pipeline_options.table_structure_options.mode.value == "accurate"


def test_docling_options_ignore_pymupdf_only_keys_and_reject_unknown():
    from vera_ingest_docling.options import DoclingOptions, describe_pipeline

    options = DoclingOptions.from_mapping(
        {
            "chunk_size": 400,
            "ocr_mode": "force",
            "ocr_language": "fr",
            "overlap": 75,
            "ocr_dpi": 300,
        }
    )
    assert options.chunk_size == 400
    assert options.ocr_mode == "force"
    assert options.ocr_language == "fr"
    assert options.pdf_backend == "docling_parse"
    with pytest.raises(ValueError, match="Unknown Docling option"):
        DoclingOptions.from_mapping({"chunk_size": 100, "bogus": True})
    with pytest.raises(ValueError, match="Unsupported pdf_backend"):
        DoclingOptions.from_mapping({"pdf_backend": "ghostscript"})

    descriptor = describe_pipeline()
    assert descriptor.installed is True
    assert {field.key for field in descriptor.fields} == {
        "chunk_size",
        "ocr_mode",
        "ocr_language",
        "pdf_backend",
    }
    assert descriptor.capabilities.overlap_supported is False
    assert descriptor.capabilities.ocr_dpi_supported is False
    assert descriptor.capabilities.chunk_unit == "tokens"
    chunk_size_field = next(field for field in descriptor.fields if field.key == "chunk_size")
    assert chunk_size_field.unit == "tokens"
    assert "whitespace-split words" in chunk_size_field.description


def test_build_converter_respects_pdf_backend_option():
    from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend

    from vera_ingest_docling.options import DoclingOptions
    from vera_ingest_docling.pipeline import _build_converter

    default = _build_converter(DoclingOptions.from_mapping({}))
    default_backend = default.format_to_options["pdf"].backend
    assert default_backend is not PyPdfiumDocumentBackend

    pypdfium = _build_converter(
        DoclingOptions.from_mapping({"pdf_backend": "pypdfium2"}),
    )
    assert pypdfium.format_to_options["pdf"].backend is PyPdfiumDocumentBackend

    overridden = _build_converter(
        DoclingOptions.from_mapping({"pdf_backend": "docling_parse"}),
        backend="pypdfium2",
    )
    assert overridden.format_to_options["pdf"].backend is PyPdfiumDocumentBackend


def test_pipeline_maps_hybrid_chunks_with_monkeypatched_conversion(monkeypatch, tmp_path):
    document = _fixture_document()

    class Result:
        status = ConversionStatus.SUCCESS

        def __init__(self, doc):
            self.document = doc

    class Converter:
        def convert(self, source=None, raises_on_error=True, **_kwargs):
            assert str(source).endswith(".pdf")
            assert raises_on_error is False
            return Result(document)

    monkeypatch.setattr(
        "vera_ingest_docling.converter._build_converter",
        lambda options, **_kwargs: Converter(),
    )

    pdf = tmp_path / "fixture.pdf"
    pdf.write_bytes(b"%PDF-1.4 fixture")
    pipeline = DoclingHybridPipeline()
    result = pipeline(
        str(pdf),
        IngestRequest(
            pipeline_options={"chunk_size": 100, "ocr_mode": "auto"},
        ),
    )

    assert result.parser_name == "docling"
    assert result.parser_version
    assert "docling_hybrid" in result.chunking_strategy
    assert result.diagnostics["overlap_ignored"] is True
    assert result.diagnostics["layout_engine"] == "onnxruntime"
    assert result.diagnostics["tableformer_mode"] == "accurate"
    assert result.diagnostics["pdf_backend"] == "docling_parse"
    assert result.diagnostics["recovered_pages"] == []
    assert "ocr_dpi" not in result.diagnostics
    assert "overlap_requested" not in result.diagnostics
    assert result.chunks
    assert any(chunk.heading_path for chunk in result.chunks)
    assert any(chunk.embedding_text for chunk in result.chunks)
    assert {block.block_id for block in result.blocks}
    image_ids = {
        block.block_id
        for block in result.blocks
        if block.block_type == "image" and block.image_bytes
    }
    assert image_ids
    assert any(image_ids.intersection(chunk.block_ids) for chunk in result.chunks)


def test_prepare_does_not_forward_pymupdf_overlap_dpi_to_docling():
    from vera_ingest import prepare_pipeline_options
    from vera_ingest_docling.options import DoclingOptions

    merged = prepare_pipeline_options(
        spec="docling",
        legacy_options={
            "chunk_size": 500,
            "overlap": 75,
            "ocr_mode": "auto",
            "ocr_language": "eng",
            "ocr_dpi": 300,
            "ocr_download": False,
        },
        pipeline_options={"chunk_size": 250},
    )
    assert merged == {
        "chunk_size": 250,
        "ocr_mode": "auto",
    }
    assert "ocr_language" not in merged
    assert "overlap" not in merged
    assert "ocr_dpi" not in merged
    assert "ocr_download" not in merged
    assert DoclingOptions.from_mapping(merged).ocr_language == "en"

    explicit = prepare_pipeline_options(
        spec="docling",
        legacy_options={"ocr_language": "eng", "ocr_mode": "auto"},
        pipeline_options={"ocr_language": "fr"},
    )
    assert explicit["ocr_language"] == "fr"


def test_convert_docling_resolves_ocr_language_to_pipeline_default(monkeypatch, tmp_path):
    document = _fixture_document()
    captured = {}

    class Result:
        status = ConversionStatus.SUCCESS

        def __init__(self, doc):
            self.document = doc

    class Converter:
        def convert(self, source=None, **_kwargs):
            return Result(document)

    def fake_build(options, **_kwargs):
        captured["options"] = options
        return Converter()

    monkeypatch.setattr("vera_ingest_docling.converter._build_converter", fake_build)

    pdf = tmp_path / "source.pdf"
    out = tmp_path / "source.vera"
    pdf.write_bytes(b"%PDF-1.4 retained")

    class Embedder:
        model_name = "hashing-test"
        dimension = 4
        normalization = "l2"

        def embed(self, texts):
            vector = np.asarray([0.5, 0.5, 0.5, 0.5], dtype=np.float32)
            return np.vstack([vector for _ in texts])

    convert(
        str(pdf),
        str(out),
        parser="docling",
        embedding_function=Embedder(),
        store_original=False,
    )

    assert captured["options"].ocr_language == "en"
    assert captured["options"].ocr_language != "eng"


def test_partial_success_is_rejected(monkeypatch, tmp_path):
    fixture = _fixture_document()

    class Result:
        status = ConversionStatus.PARTIAL_SUCCESS
        errors: list[object] = []

        def __init__(self, doc):
            self.document = doc

    class Converter:
        def convert(self, source=None, **_kwargs):
            return Result(fixture)

    monkeypatch.setattr(
        "vera_ingest_docling.converter._build_converter",
        lambda options, **_kwargs: Converter(),
    )
    pdf = tmp_path / "partial.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    with pytest.raises(ValueError, match="did not fully succeed"):
        DoclingHybridPipeline()(str(pdf), IngestRequest())


def test_convert_uses_docling_pipeline_end_to_end(monkeypatch, tmp_path):
    document = _fixture_document()

    class Result:
        status = ConversionStatus.SUCCESS

        def __init__(self, doc):
            self.document = doc

    class Converter:
        def convert(self, source=None, **_kwargs):
            return Result(document)

    monkeypatch.setattr(
        "vera_ingest_docling.converter._build_converter",
        lambda options, **_kwargs: Converter(),
    )

    pdf = tmp_path / "source.pdf"
    out = tmp_path / "source.vera"
    pdf.write_bytes(b"%PDF-1.4 retained")

    class Embedder:
        model_name = "hashing-test"
        dimension = 4
        normalization = "l2"

        def embed(self, texts):
            vector = np.asarray([0.5, 0.5, 0.5, 0.5], dtype=np.float32)
            return np.vstack([vector for _ in texts])

    convert(
        str(pdf),
        str(out),
        parser="docling",
        embedding_function=Embedder(),
        store_original=False,
    )
    with VeraDocument.open(str(out), embedding_function=Embedder()) as document_archive:
        info = document_archive.inspect()
        assert info["parser_name"] == "docling"
        hits = document_archive.search("detention", mode="keyword", top_k=3)
        assert hits
        from vera_ingest.viewer import figures, figures_for

        stored = figures(document_archive)
        assert stored
        assert stored[0].get("caption")
        caption_hits = document_archive.search("Figure 1", mode="keyword", top_k=3)
        assert caption_hits
        assert figures_for(document_archive, caption_hits[0])


def _page_failed_error(zero_based_page: int, detail: str = "std::bad_alloc") -> ErrorItem:
    """Build a real Docling 2.118 ErrorItem (no page_no field)."""
    item = ErrorItem(
        component_type=DoclingComponentType.DOCUMENT_BACKEND,
        module_name="DoclingParseDocumentBackend",
        error_message=f"Page {zero_based_page} failed to parse. {detail}",
    )
    # Real Docling ErrorItem either omits page_no or leaves it unset.
    assert getattr(item, "page_no", None) is None
    return item


def _memory_error(detail: str = "std::bad_alloc") -> ErrorItem:
    item = ErrorItem(
        component_type=DoclingComponentType.DOCUMENT_BACKEND,
        module_name="DoclingParseDocumentBackend",
        error_message=detail,
    )
    assert getattr(item, "page_no", None) is None
    return item


def _multi_page_document(
    page_count: int = 5,
    *,
    missing_pages: set[int] | None = None,
    omit_pages: set[int] | None = None,
) -> DoclingDocument:
    """Build a multi-page fixture; omit text and/or page entries to simulate failures."""
    missing = missing_pages or set()
    omitted = omit_pages or set()
    doc = DoclingDocument(name="multi")
    for page_no in range(1, page_count + 1):
        if page_no in omitted:
            continue
        doc.add_page(page_no=page_no, size=Size(width=612.0, height=792.0))
        if page_no in missing:
            continue
        doc.add_text(
            label=DocItemLabel.PARAGRAPH,
            text=f"Recoverable content on page {page_no}.",
            prov=_prov(page_no, 72, 640, 500, 680),
        )
    return doc


def _single_page_document(page_no: int, text: str) -> DoclingDocument:
    doc = DoclingDocument(name=f"page-{page_no}")
    doc.add_page(page_no=page_no, size=Size(width=612.0, height=792.0))
    doc.add_text(
        label=DocItemLabel.PARAGRAPH,
        text=text,
        prov=_prov(page_no, 72, 640, 500, 680),
    )
    return doc


def test_partial_success_with_page_errors_recovers_via_fresh_retry(monkeypatch, tmp_path):
    partial_doc = _multi_page_document(5, missing_pages={2})
    recovered_doc = _single_page_document(2, "Recovered page two text about ponds.")
    calls: list[dict[str, object]] = []

    class PartialResult:
        status = ConversionStatus.PARTIAL_SUCCESS
        errors = [_page_failed_error(1, "Stage preprocess failed: std::bad_alloc")]

        def __init__(self, doc):
            self.document = doc

    class SuccessResult:
        status = ConversionStatus.SUCCESS

        def __init__(self, doc):
            self.document = doc

    class Converter:
        def __init__(self, backend: str | None):
            self.backend = backend or "docling_parse"

        def convert(self, source=None, page_range=None, raises_on_error=True, **_kwargs):
            calls.append(
                {
                    "backend": self.backend,
                    "page_range": page_range,
                    "raises_on_error": raises_on_error,
                }
            )
            if page_range is None:
                return PartialResult(partial_doc)
            assert page_range == (2, 2)
            assert self.backend == "docling_parse"
            return SuccessResult(recovered_doc)

    monkeypatch.setattr(
        "vera_ingest_docling.converter._build_converter",
        lambda options, backend=None, **_kwargs: Converter(backend),
    )

    pdf = tmp_path / "recover.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    result = DoclingHybridPipeline()(
        str(pdf),
        IngestRequest(pipeline_options={"chunk_size": 100}),
    )
    assert result.diagnostics["recovered_pages"] == [2]
    assert result.diagnostics["recovered_pages_backend"] == {"2": "docling_parse"}
    assert any("Recovered page two" in chunk.text for chunk in result.chunks)
    assert any(call["page_range"] == (2, 2) for call in calls)
    assert all(call["raises_on_error"] is False for call in calls)


def test_page_recovery_falls_back_to_pypdfium2_per_page(monkeypatch, tmp_path):
    partial_doc = _multi_page_document(5, missing_pages={2})
    recovered_doc = _single_page_document(2, "Pypdfium recovered page two.")
    calls: list[dict[str, object]] = []

    class PartialResult:
        status = ConversionStatus.PARTIAL_SUCCESS
        errors = [_page_failed_error(1)]

        def __init__(self, doc):
            self.document = doc

    class FailResult:
        status = ConversionStatus.FAILURE
        errors = [_page_failed_error(1, "std::bad_alloc again")]
        document = None

    class SuccessResult:
        status = ConversionStatus.SUCCESS

        def __init__(self, doc):
            self.document = doc

    class Converter:
        def __init__(self, backend: str | None):
            self.backend = backend or "docling_parse"

        def convert(self, source=None, page_range=None, raises_on_error=True, **_kwargs):
            calls.append(
                {
                    "backend": self.backend,
                    "page_range": page_range,
                    "raises_on_error": raises_on_error,
                }
            )
            if page_range is None:
                return PartialResult(partial_doc)
            if self.backend == "docling_parse":
                return FailResult()
            assert self.backend == "pypdfium2"
            return SuccessResult(recovered_doc)

    monkeypatch.setattr(
        "vera_ingest_docling.converter._build_converter",
        lambda options, backend=None, **_kwargs: Converter(backend),
    )

    pdf = tmp_path / "recover-pypdfium.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    result = DoclingHybridPipeline()(str(pdf), IngestRequest())
    assert result.diagnostics["recovered_pages"] == [2]
    assert result.diagnostics["recovered_pages_backend"] == {"2": "pypdfium2"}
    assert any("Pypdfium recovered" in chunk.text for chunk in result.chunks)
    assert any(
        call["backend"] == "docling_parse" and call["page_range"] == (2, 2) for call in calls
    )
    assert any(call["backend"] == "pypdfium2" and call["page_range"] == (2, 2) for call in calls)
    assert all(call["raises_on_error"] is False for call in calls)


def test_too_many_failed_pages_falls_back_to_whole_document_pypdfium2(monkeypatch, tmp_path):
    # 3/5 failed pages => 0.6 > 0.2 cap => whole-document pypdfium2.
    partial_doc = _multi_page_document(5, missing_pages={2, 3, 4})
    full_doc = _multi_page_document(5)
    calls: list[dict[str, object]] = []

    class PartialResult:
        status = ConversionStatus.PARTIAL_SUCCESS
        errors = [
            _page_failed_error(1),
            _page_failed_error(2),
            _page_failed_error(3),
        ]

        def __init__(self, doc):
            self.document = doc

    class SuccessResult:
        status = ConversionStatus.SUCCESS

        def __init__(self, doc):
            self.document = doc

    class Converter:
        def __init__(self, backend: str | None):
            self.backend = backend or "docling_parse"

        def convert(self, source=None, page_range=None, raises_on_error=True, **_kwargs):
            calls.append(
                {
                    "backend": self.backend,
                    "page_range": page_range,
                    "raises_on_error": raises_on_error,
                }
            )
            if page_range is not None:
                raise AssertionError("per-page recovery should be skipped when over cap")
            if self.backend == "pypdfium2":
                return SuccessResult(full_doc)
            return PartialResult(partial_doc)

    monkeypatch.setattr(
        "vera_ingest_docling.converter._build_converter",
        lambda options, backend=None, **_kwargs: Converter(backend),
    )

    pdf = tmp_path / "many-fail.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    result = DoclingHybridPipeline()(str(pdf), IngestRequest())
    assert result.diagnostics["whole_document_fallback_backend"] == "pypdfium2"
    assert result.diagnostics["pdf_backend"] == "pypdfium2"
    assert result.diagnostics["recovered_pages"] == []
    assert any(call["backend"] == "pypdfium2" and call["page_range"] is None for call in calls)
    assert all(call["raises_on_error"] is False for call in calls)


def test_convert_exception_triggers_whole_document_pypdfium2_fallback(monkeypatch, tmp_path):
    full_doc = _multi_page_document(3)
    calls: list[dict[str, object]] = []

    class SuccessResult:
        status = ConversionStatus.SUCCESS

        def __init__(self, doc):
            self.document = doc

    class Converter:
        def __init__(self, backend: str | None):
            self.backend = backend or "docling_parse"

        def convert(self, source=None, page_range=None, raises_on_error=True, **_kwargs):
            calls.append(
                {
                    "backend": self.backend,
                    "page_range": page_range,
                    "raises_on_error": raises_on_error,
                }
            )
            if self.backend != "pypdfium2":
                raise RuntimeError("native crash")
            return SuccessResult(full_doc)

    monkeypatch.setattr(
        "vera_ingest_docling.converter._build_converter",
        lambda options, backend=None, **_kwargs: Converter(backend),
    )

    pdf = tmp_path / "crash.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    result = DoclingHybridPipeline()(str(pdf), IngestRequest())
    assert result.diagnostics["whole_document_fallback_backend"] == "pypdfium2"
    assert result.chunks
    assert any(call["backend"] == "pypdfium2" for call in calls)
    assert all(call["raises_on_error"] is False for call in calls)


def test_unrecoverable_page_still_raises_with_page_detail(monkeypatch, tmp_path):
    partial_doc = _multi_page_document(5, missing_pages={2})

    class PartialResult:
        status = ConversionStatus.PARTIAL_SUCCESS
        errors = [_page_failed_error(1)]

        def __init__(self, doc):
            self.document = doc

    class FailResult:
        status = ConversionStatus.FAILURE
        errors = [_page_failed_error(1, "std::bad_alloc again")]
        document = None

    class Converter:
        def __init__(self, backend: str | None):
            self.backend = backend or "docling_parse"

        def convert(self, source=None, page_range=None, raises_on_error=True, **_kwargs):
            if page_range is None:
                return PartialResult(partial_doc)
            return FailResult()

    monkeypatch.setattr(
        "vera_ingest_docling.converter._build_converter",
        lambda options, backend=None, **_kwargs: Converter(backend),
    )

    pdf = tmp_path / "unrecoverable.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    with pytest.raises(ValueError, match=r"unrecoverable pages: 2"):
        DoclingHybridPipeline()(str(pdf), IngestRequest())


def test_real_error_item_has_no_page_no():
    item = _page_failed_error(1)
    assert getattr(item, "page_no", None) is None


def test_page_from_error_entry_zero_based_message_and_page_no():
    from types import SimpleNamespace

    from vera_ingest_docling.recovery import _page_from_error_entry

    from_message = _page_from_error_entry(
        SimpleNamespace(error_message="Page 0 failed to parse.", page_no=None)
    )
    assert from_message == 1
    leftover_zero = _page_from_error_entry(SimpleNamespace(error_message="", page_no=0))
    assert leftover_zero == 1
    already_one_based = _page_from_error_entry(SimpleNamespace(error_message="", page_no=5))
    assert already_one_based == 5
    assert _page_from_error_entry(SimpleNamespace(error_message="", page_no=-1)) is None
    assert _page_from_error_entry(SimpleNamespace(error_message="", page_no="x")) is None


def test_format_docling_errors_truncates_and_adds_recovery_hints():
    from types import SimpleNamespace

    from vera_ingest_docling.recovery import _format_docling_errors

    empty = SimpleNamespace(errors=[])
    assert _format_docling_errors(empty) == ""

    many = SimpleNamespace(
        errors=[SimpleNamespace(error_message=f"error {index}") for index in range(7)]
    )
    formatted = _format_docling_errors(many)
    assert "error 0" in formatted
    assert "error 4" in formatted
    assert "error 5" not in formatted
    assert "+2 more" in formatted

    compile_fail = SimpleNamespace(
        errors=[SimpleNamespace(error_message="Compiler: cl is not found")]
    )
    compile_text = _format_docling_errors(compile_fail)
    assert "torch.compile" in compile_text

    oom = SimpleNamespace(errors=[SimpleNamespace(error_message="std::bad_alloc")])
    oom_text = _format_docling_errors(oom)
    assert "pypdfium2" in oom_text
    assert "out of memory" in oom_text.lower() or "ran out of memory" in oom_text.lower()


def test_memory_error_without_page_falls_back_to_whole_pypdfium2(monkeypatch, tmp_path):
    partial_doc = _multi_page_document(5, missing_pages={2})
    full_doc = _multi_page_document(5)
    calls: list[dict[str, object]] = []

    class PartialResult:
        status = ConversionStatus.PARTIAL_SUCCESS
        errors = [_memory_error("std::bad_alloc")]

        def __init__(self, doc):
            self.document = doc

    class SuccessResult:
        status = ConversionStatus.SUCCESS

        def __init__(self, doc):
            self.document = doc

    class Converter:
        def __init__(self, backend: str | None):
            self.backend = backend or "docling_parse"

        def convert(self, source=None, page_range=None, raises_on_error=True, **_kwargs):
            calls.append({"backend": self.backend, "page_range": page_range})
            if page_range is not None:
                raise AssertionError("per-page recovery needs attributable pages")
            if self.backend == "pypdfium2":
                return SuccessResult(full_doc)
            return PartialResult(partial_doc)

    monkeypatch.setattr(
        "vera_ingest_docling.converter._build_converter",
        lambda options, backend=None, **_kwargs: Converter(backend),
    )

    pdf = tmp_path / "no-page.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    result = DoclingHybridPipeline()(str(pdf), IngestRequest())
    assert result.diagnostics["whole_document_fallback_backend"] == "pypdfium2"
    assert result.diagnostics["recovered_pages"] == []
    assert any(call["backend"] == "pypdfium2" and call["page_range"] is None for call in calls)


def test_missing_pages_inferred_from_page_count_diff(monkeypatch, tmp_path):
    partial_doc = _multi_page_document(5, omit_pages={2})
    recovered_doc = _single_page_document(2, "Recovered via page-count diff.")
    calls: list[dict[str, object]] = []

    class _Input:
        page_count = 5

    class PartialResult:
        status = ConversionStatus.PARTIAL_SUCCESS
        errors = [_memory_error("std::bad_alloc")]
        input = _Input()

        def __init__(self, doc):
            self.document = doc

    class SuccessResult:
        status = ConversionStatus.SUCCESS

        def __init__(self, doc):
            self.document = doc

    class Converter:
        def __init__(self, backend: str | None):
            self.backend = backend or "docling_parse"

        def convert(self, source=None, page_range=None, **_kwargs):
            calls.append({"backend": self.backend, "page_range": page_range})
            if page_range is None:
                return PartialResult(partial_doc)
            assert page_range == (2, 2)
            return SuccessResult(recovered_doc)

    monkeypatch.setattr(
        "vera_ingest_docling.converter._build_converter",
        lambda options, backend=None, **_kwargs: Converter(backend),
    )

    pdf = tmp_path / "diff-pages.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    result = DoclingHybridPipeline()(str(pdf), IngestRequest())
    assert result.diagnostics["recovered_pages"] == [2]
    assert any("Recovered via page-count diff" in chunk.text for chunk in result.chunks)
    assert any(call["page_range"] == (2, 2) for call in calls)


def test_spanning_hybrid_chunk_overlapping_failed_page_is_dropped(monkeypatch, tmp_path):
    partial_doc = _multi_page_document(5, missing_pages={2})
    recovered_doc = _single_page_document(2, "Recovered page two after span drop.")

    def fake_chunk_document(document, blocks, config):
        pages = getattr(document, "pages", None) or {}
        if len(pages) == 1:
            return [
                IngestChunk(
                    chunk_id="chunk_000001",
                    text="Recovered page two after span drop.",
                    page_start=1,
                    page_end=1,
                    heading_path="",
                    token_count=6,
                )
            ]
        return [
            IngestChunk(
                chunk_id="chunk_000001",
                text="stale spanning text that includes failed page two",
                page_start=1,
                page_end=3,
                heading_path="Chapter 1",
                token_count=8,
            )
        ]

    class PartialResult:
        status = ConversionStatus.PARTIAL_SUCCESS
        errors = [_page_failed_error(1)]

        def __init__(self, doc):
            self.document = doc

    class SuccessResult:
        status = ConversionStatus.SUCCESS

        def __init__(self, doc):
            self.document = doc

    class Converter:
        def __init__(self, backend: str | None):
            self.backend = backend or "docling_parse"

        def convert(self, source=None, page_range=None, **_kwargs):
            if page_range is None:
                return PartialResult(partial_doc)
            return SuccessResult(recovered_doc)

    monkeypatch.setattr(
        "vera_ingest_docling.converter._build_converter",
        lambda options, backend=None, **_kwargs: Converter(backend),
    )
    monkeypatch.setattr(
        "vera_ingest_docling.recovery._chunk_document",
        fake_chunk_document,
    )

    pdf = tmp_path / "span.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    result = DoclingHybridPipeline()(str(pdf), IngestRequest())
    assert all("stale spanning" not in chunk.text for chunk in result.chunks)
    assert any("Recovered page two after span drop" in chunk.text for chunk in result.chunks)


def test_forced_pypdfium2_skips_docling_parse_page_retry(monkeypatch, tmp_path):
    partial_doc = _multi_page_document(5, missing_pages={2})
    recovered_doc = _single_page_document(2, "Forced pypdfium recovered page two.")
    calls: list[dict[str, object]] = []

    class PartialResult:
        status = ConversionStatus.PARTIAL_SUCCESS
        errors = [_page_failed_error(1)]

        def __init__(self, doc):
            self.document = doc

    class SuccessResult:
        status = ConversionStatus.SUCCESS

        def __init__(self, doc):
            self.document = doc

    class Converter:
        def __init__(self, backend: str | None):
            self.backend = backend or "docling_parse"

        def convert(self, source=None, page_range=None, **_kwargs):
            calls.append({"backend": self.backend, "page_range": page_range})
            if page_range is None:
                return PartialResult(partial_doc)
            assert self.backend == "pypdfium2"
            return SuccessResult(recovered_doc)

    monkeypatch.setattr(
        "vera_ingest_docling.converter._build_converter",
        lambda options, backend=None, **_kwargs: Converter(backend),
    )

    pdf = tmp_path / "forced.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    result = DoclingHybridPipeline()(
        str(pdf),
        IngestRequest(pipeline_options={"pdf_backend": "pypdfium2"}),
    )
    assert result.diagnostics["recovered_pages"] == [2]
    assert result.diagnostics["recovered_pages_backend"] == {"2": "pypdfium2"}
    assert not any(
        call["backend"] == "docling_parse" and call["page_range"] is not None for call in calls
    )
    assert any(call["backend"] == "pypdfium2" and call["page_range"] == (2, 2) for call in calls)


def test_docling_options_from_mapping_remaps_tesseract_eng():
    from vera_ingest_docling.options import DoclingOptions

    assert DoclingOptions.from_mapping({"ocr_language": "eng"}).ocr_language == "en"
    assert DoclingOptions.from_mapping({"ocr_language": "ENG"}).ocr_language == "en"
    assert DoclingOptions.from_mapping({"ocr_language": "eng+fr"}).ocr_language == "en+fr"
    assert DoclingOptions.from_mapping({"ocr_language": "fr"}).ocr_language == "fr"


def test_pipeline_ingest_options_does_not_leak_tesseract_eng(monkeypatch, tmp_path):
    document = _fixture_document()
    captured: dict[str, object] = {}

    class Result:
        status = ConversionStatus.SUCCESS

        def __init__(self, doc):
            self.document = doc

    class Converter:
        def convert(self, source=None, **_kwargs):
            return Result(document)

    def fake_build(options, **_kwargs):
        captured["options"] = options
        return Converter()

    monkeypatch.setattr("vera_ingest_docling.converter._build_converter", fake_build)

    pdf = tmp_path / "legacy.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    result = DoclingHybridPipeline()(str(pdf), IngestOptions())
    assert captured["options"].ocr_language == "en"
    assert result.diagnostics["ocr_language"] == "en"
    assert result.diagnostics["ocr_languages"] == ["en"]


def test_cancelled_error_is_not_swallowed(monkeypatch, tmp_path):
    class CancelledError(RuntimeError):
        pass

    class Converter:
        def convert(self, source=None, **_kwargs):
            raise CancelledError("user cancelled")

    monkeypatch.setattr(
        "vera_ingest_docling.converter._build_converter",
        lambda options, **_kwargs: Converter(),
    )
    pdf = tmp_path / "cancel.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    with pytest.raises(CancelledError, match="user cancelled"):
        DoclingHybridPipeline()(str(pdf), IngestRequest())


def test_fallback_failure_preserves_original_exception_as_cause(monkeypatch, tmp_path, capsys):
    class Converter:
        def convert(self, source=None, **_kwargs):
            raise RuntimeError("std::bad_alloc native crash")

    monkeypatch.setattr(
        "vera_ingest_docling.converter._build_converter",
        lambda options, **_kwargs: Converter(),
    )
    monkeypatch.setattr("vera_ingest_docling.recovery._pdf_page_count", lambda _path: 2)
    monkeypatch.setattr("vera_ingest_docling.recovery._FALLBACK_BATCH_PAGES", 2)
    pdf = tmp_path / "both-fail.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    with pytest.raises(ValueError, match="pypdfium2") as info:
        DoclingHybridPipeline()(str(pdf), IngestRequest())
    assert info.value.__cause__ is not None
    assert "bad_alloc" in str(info.value.__cause__)
    assert "RuntimeError" in str(info.value)
    assert "bad_alloc" in str(info.value)
    err = capsys.readouterr().err
    assert "Docling convert failed" in err


def test_whole_pypdfium2_exception_falls_back_to_batched_pages(monkeypatch, tmp_path):
    calls: list[dict[str, object]] = []

    class SuccessResult:
        status = ConversionStatus.SUCCESS

        def __init__(self, doc):
            self.document = doc

    class Converter:
        def __init__(self, backend: str | None):
            self.backend = backend or "docling_parse"

        def convert(self, source=None, page_range=None, raises_on_error=True, **_kwargs):
            calls.append({"backend": self.backend, "page_range": page_range})
            if page_range is None:
                raise RuntimeError("whole document OOM")
            start, end = page_range
            doc = DoclingDocument(name="batch")
            for page_no in range(start, end + 1):
                doc.add_page(page_no=page_no, size=Size(width=612.0, height=792.0))
                doc.add_text(
                    label=DocItemLabel.PARAGRAPH,
                    text=f"Batched content on page {page_no}.",
                    prov=_prov(page_no, 72, 640, 500, 680),
                )
            return SuccessResult(doc)

    monkeypatch.setattr(
        "vera_ingest_docling.converter._build_converter",
        lambda options, backend=None, **_kwargs: Converter(backend),
    )
    monkeypatch.setattr("vera_ingest_docling.recovery._pdf_page_count", lambda _path: 3)
    monkeypatch.setattr("vera_ingest_docling.recovery._FALLBACK_BATCH_PAGES", 2)

    pdf = tmp_path / "batched.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    result = DoclingHybridPipeline()(str(pdf), IngestRequest())
    assert result.diagnostics["whole_document_fallback_backend"] == "pypdfium2"
    assert result.diagnostics["whole_document_fallback_strategy"] == "batched"
    texts = " ".join(chunk.text for chunk in result.chunks)
    assert "Batched content on page 1" in texts
    assert "Batched content on page 3" in texts
    assert any(call["backend"] == "pypdfium2" and call["page_range"] == (1, 2) for call in calls)
    assert any(call["backend"] == "pypdfium2" and call["page_range"] == (3, 3) for call in calls)


def test_picture_item_does_not_stringify_caption_refs():
    item = PictureItem(
        self_ref="#/pictures/0",
        captions=[RefItem(cref="#/texts/5")],
    )
    text = _item_text(None, item, "image")
    assert "RefItem" not in text
    assert "#/texts/5" not in text
    assert text == ""


def test_hybrid_chunks_link_picture_blocks_to_same_page_caption():
    from vera_ingest_docling.options import DoclingOptions

    document = _fixture_document()
    _pages, blocks = map_docling_document(document)
    images = [block for block in blocks if block.block_type == "image"]
    assert images
    assert images[0].image_bytes
    chunks = _chunk_document(
        document,
        blocks,
        DoclingOptions.from_mapping({"chunk_size": 100}),
    )
    image_ids = {block.block_id for block in images}
    linked = {block_id for chunk in chunks for block_id in chunk.block_ids}
    assert image_ids <= linked
    caption_chunks = [chunk for chunk in chunks if "Figure 1" in chunk.text]
    assert caption_chunks
    assert image_ids.intersection(caption_chunks[0].block_ids)


def test_uncaptioned_picture_is_linked_to_same_page_text_chunk():
    from docling_core.types.doc import ImageRef

    from vera_ingest_docling.options import DoclingOptions

    document = DoclingDocument(name="uncaptioned")
    document.add_page(page_no=1, size=Size(width=612.0, height=792.0))
    document.add_text(
        label=DocItemLabel.PARAGRAPH,
        text="Nearby paragraph about detention ponds.",
        prov=_prov(1, 72, 640, 500, 680),
    )
    image = Image.new("RGB", (32, 32), color=(20, 40, 60))
    document.add_picture(
        prov=_prov(1, 350, 400, 500, 500),
        image=ImageRef.from_pil(image=image, dpi=72),
    )
    _pages, blocks = map_docling_document(document)
    images = [block for block in blocks if block.block_type == "image"]
    assert len(images) == 1
    assert images[0].image_bytes
    chunks = _chunk_document(
        document,
        blocks,
        DoclingOptions.from_mapping({"chunk_size": 100}),
    )
    assert any(images[0].block_id in chunk.block_ids for chunk in chunks)
    assert any("detention ponds" in chunk.text for chunk in chunks)


@pytest.mark.docling_integration
@pytest.mark.skipif(
    __import__("os").environ.get("VERA_RUN_DOCLING_INTEGRATION") != "1",
    reason="Set VERA_RUN_DOCLING_INTEGRATION=1 after prefetching Docling models",
)
def test_real_pdf_docling_integration(tmp_path):
    import fitz

    pdf = tmp_path / "real.pdf"
    out = tmp_path / "real.vera"
    source = fitz.open()
    page = source.new_page()
    page.insert_text((72, 72), "Integration stormwater detention requirements.")
    source.save(pdf)
    source.close()

    convert(str(pdf), str(out), parser="docling", model="hashing", store_original=False)
    with VeraDocument.open(str(out)) as document:
        assert document.inspect()["parser_name"] == "docling"
        assert document.search("detention", mode="keyword", top_k=1)
