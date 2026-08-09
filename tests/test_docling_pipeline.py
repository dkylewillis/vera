"""Offline Docling ingest pipeline tests (no model/network downloads)."""

from __future__ import annotations

import io

import numpy as np
import pytest

pytest.importorskip("docling")
pytest.importorskip("docling_core")

from docling.datamodel.base_models import ConversionStatus
from docling_core.types.doc import (
    DocItemLabel,
    DoclingDocument,
    ProvenanceItem,
)
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from PIL import Image
from vera import VeraDocument
from vera_ingest import (
    UnknownIngestPipelineError,
    convert,
    get_ingest_pipeline,
    list_ingest_pipelines,
    reset_ingest_pipeline_registry,
)

from vera_ingest_docling import create_pipeline
from vera_ingest_docling.pipeline import (
    DoclingHybridPipeline,
    WhitespaceTokenizer,
    map_docling_document,
    map_rapidocr_languages,
)


pytestmark = pytest.mark.docling


@pytest.fixture(autouse=True)
def isolated_registry():
    reset_ingest_pipeline_registry()
    yield
    reset_ingest_pipeline_registry()


def _prov(page_no: int, l: float, b: float, r: float, t: float, height: float = 792.0) -> ProvenanceItem:
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
    assert headings[0].block_id.startswith("texts_") or "heading" in headings[0].block_id or headings[0].block_id
    # Bottom-left (72,700)-(300,720) on 792-tall page -> top-left y = 72 and 92.
    assert headings[0].bbox is not None
    left, top, right, bottom = headings[0].bbox
    assert left == pytest.approx(72.0)
    assert right == pytest.approx(300.0)
    assert top == pytest.approx(72.0)
    assert bottom == pytest.approx(92.0)
    assert any("detention ponds" in block.text for block in paragraphs)
    assert any("Figure 1" in block.text for block in captions)
    if images:
        assert images[0].image_bytes
        assert images[0].image_ext == "png"


def test_whitespace_tokenizer_is_deterministic():
    tokenizer = WhitespaceTokenizer(max_tokens=12)
    assert tokenizer.count_tokens("one two three") == 3
    assert tokenizer.get_max_tokens() == 12
    assert tokenizer.get_tokenizer()("a b") == 2


def test_map_rapidocr_languages_translates_tesseract_defaults():
    assert map_rapidocr_languages(None) == ["en"]
    assert map_rapidocr_languages("") == ["en"]
    assert map_rapidocr_languages("eng") == ["en"]
    assert map_rapidocr_languages("eng+fra") == ["en", "fr"]
    assert map_rapidocr_languages("en,de") == ["en", "de"]
    assert map_rapidocr_languages("jpn") == ["japan"]
    assert map_rapidocr_languages("chi_sim") == ["ch"]
    with pytest.raises(ValueError, match="does not support OCR language"):
        map_rapidocr_languages("not-a-language")


def test_build_converter_maps_default_eng_to_rapidocr_en():
    from vera_ingest_docling.options import DoclingOptions
    from vera_ingest_docling.pipeline import _build_converter

    converter = _build_converter(
        DoclingOptions.from_mapping({"ocr_mode": "auto", "ocr_language": "eng"}),
    )
    pdf_option = converter.format_to_options["pdf"]
    assert pdf_option.pipeline_options.do_ocr is True
    assert list(pdf_option.pipeline_options.ocr_options.lang) == ["en"]


def test_build_converter_disables_torch_compile_and_keeps_default_image_scale():
    from vera_ingest_docling.options import DoclingOptions
    from vera_ingest_docling.pipeline import _build_converter

    converter = _build_converter(
        DoclingOptions.from_mapping({"ocr_mode": "auto", "ocr_language": "eng"}),
    )
    pipeline_options = converter.format_to_options["pdf"].pipeline_options
    assert pipeline_options.images_scale == 1.0
    assert pipeline_options.layout_options.engine_options.compile_model is False


def test_docling_options_ignore_pymupdf_only_keys_and_reject_unknown():
    from vera_ingest_docling.options import DoclingOptions, describe_pipeline

    options = DoclingOptions.from_mapping(
        {
            "chunk_size": 420,
            "ocr_mode": "force",
            "ocr_language": "eng",
            "overlap": 75,
            "ocr_dpi": 300,
        }
    )
    assert options.chunk_size == 420
    assert options.ocr_mode == "force"
    assert options.ocr_language == "en"
    with pytest.raises(ValueError, match="Unknown Docling option"):
        DoclingOptions.from_mapping({"chunk_size": 100, "bogus": True})

    descriptor = describe_pipeline()
    assert {field.key for field in descriptor.fields} == {
        "chunk_size",
        "ocr_mode",
        "ocr_language",
    }
    assert descriptor.capabilities.overlap_supported is False
    assert descriptor.capabilities.ocr_dpi_supported is False
    assert descriptor.capabilities.chunk_unit == "tokens"


def test_pipeline_maps_hybrid_chunks_with_monkeypatched_conversion(monkeypatch, tmp_path):
    document = _fixture_document()

    class Result:
        status = ConversionStatus.SUCCESS

        def __init__(self, doc):
            self.document = doc

    class Converter:
        def convert(self, source):
            assert source.endswith(".pdf")
            return Result(document)

    monkeypatch.setattr(
        "vera_ingest_docling.pipeline._build_converter",
        lambda options: Converter(),
    )

    pdf = tmp_path / "fixture.pdf"
    pdf.write_bytes(b"%PDF-1.4 fixture")
    pipeline = DoclingHybridPipeline()
    from vera_ingest.types import IngestRequest

    result = pipeline.ingest(
        str(pdf),
        IngestRequest(
            pipeline_options={"chunk_size": 40, "ocr_mode": "auto"},
        ),
    )

    assert result.parser_name == "docling"
    assert result.parser_version
    assert "docling_hybrid" in result.chunking_strategy
    assert result.diagnostics["overlap_ignored"] is True
    assert "ocr_dpi" not in result.diagnostics
    assert "overlap_requested" not in result.diagnostics
    assert result.chunks
    assert any(chunk.heading_path for chunk in result.chunks)
    assert any(chunk.embedding_text for chunk in result.chunks)
    assert {block.block_id for block in result.blocks}


def test_prepare_does_not_forward_pymupdf_overlap_dpi_to_docling():
    from vera_ingest import prepare_pipeline_options

    merged = prepare_pipeline_options(
        spec="docling",
        legacy_options={
            "chunk_size": 500,
            "overlap": 75,
            "ocr_mode": "auto",
            "ocr_language": "eng",
            "ocr_dpi": 300,
        },
        pipeline_options={"chunk_size": 250},
    )
    assert merged == {
        "chunk_size": 250,
        "ocr_mode": "auto",
        "ocr_language": "eng",
    }
    assert "overlap" not in merged
    assert "ocr_dpi" not in merged


def test_partial_success_is_rejected(monkeypatch, tmp_path):
    fixture = _fixture_document()

    class Result:
        status = ConversionStatus.PARTIAL_SUCCESS

        def __init__(self, doc):
            self.document = doc

    class Converter:
        def convert(self, source):
            return Result(fixture)

    monkeypatch.setattr(
        "vera_ingest_docling.pipeline._build_converter",
        lambda options: Converter(),
    )
    pdf = tmp_path / "partial.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    from vera_ingest.types import IngestRequest

    with pytest.raises(ValueError, match="did not fully succeed"):
        DoclingHybridPipeline().ingest(str(pdf), IngestRequest())


def test_convert_uses_docling_pipeline_end_to_end(monkeypatch, tmp_path):
    document = _fixture_document()

    class Result:
        status = ConversionStatus.SUCCESS

        def __init__(self, doc):
            self.document = doc

    class Converter:
        def convert(self, source):
            return Result(document)

    monkeypatch.setattr(
        "vera_ingest_docling.pipeline._build_converter",
        lambda options: Converter(),
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
