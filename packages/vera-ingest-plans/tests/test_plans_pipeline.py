import pytest

from vera_doc import VeraDocument
from vera_ingest import convert
from vera_ingest.pipeline import describe_ingest_pipeline, list_ingest_pipeline_descriptors
from vera_ingest_plans import ensure_registered
from vera_ingest_pymupdf import parser as pdf_parser


@pytest.fixture(autouse=True)
def _registered():
    ensure_registered()


def _vector_sheet(path, *, text: str, paths: int, width: float = 2400, height: float = 1800):
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=width, height=height)
    page.insert_text((72, 72), text, fontsize=12)
    for index in range(paths):
        y = 120 + (index % 1500)
        page.draw_line((80, y), (width - 80, y))
    doc.save(path)
    doc.close()


def _drawn_title_content():
    return (
        "raw",
        {
            "blocks": [
                {
                    "type": 0,
                    "bbox": (80.0, 400.0, 700.0, 460.0),
                    "lines": [
                        {
                            "dir": (1.0, 0.0),
                            "spans": [
                                {
                                    "text": "SADDLE BLOCKING",
                                    "bbox": (80.0, 400.0, 700.0, 460.0),
                                    "size": 14.0,
                                    "flags": 0,
                                }
                            ],
                        }
                    ],
                }
            ]
        },
    )


def test_plans_descriptor_adds_drawn_text_ocr_to_the_pymupdf_fields():
    plans = describe_ingest_pipeline("plans")
    default = describe_ingest_pipeline("pymupdf")
    assert plans.spec == "plans"
    assert plans.provider == "plans"
    assert plans.variant == ""
    assert plans.field_keys() == default.field_keys() | {"ocr_drawn_text"}
    assert plans.defaults()["ocr_drawn_text"] == "auto"
    assert plans.capabilities.source_formats == ("pdf",)
    assert "plans" in [item.spec for item in list_ingest_pipeline_descriptors()]


def test_plans_ocrs_drawing_sheets_and_keeps_titles_searchable(tmp_path, monkeypatch):
    pdf = tmp_path / "details.pdf"
    _vector_sheet(pdf, text="C705 CONSTRUCTION DETAILS", paths=2000)
    calls = []

    def fake_ocr(page, *, language, dpi, allow_download=False):
        calls.append(page.number + 1)
        return _drawn_title_content()

    monkeypatch.setattr(pdf_parser, "_ocr_page_content", fake_ocr)

    plans_out = tmp_path / "plans.vera"
    convert(str(pdf), str(plans_out), model="hashing", parser="plans")
    assert calls == [1]
    document = VeraDocument.open(str(plans_out))
    try:
        info = document.inspect()
        assert info["parser_name"] == "plans"
        assert info["ocr"]["ocr_drawn_text"] == "auto"
        assert info["ocr"]["ocr_drawn_text_pages"] == [1]
        hit = document.search("saddle blocking", mode="keyword", top_k=1)[0]
        assert hit.page_start == 1
    finally:
        document.close()

    convert(
        str(pdf),
        str(tmp_path / "plans-off.vera"),
        model="hashing",
        parser="plans",
        pipeline_options={"ocr_drawn_text": "off"},
    )
    assert calls == [1]


def test_plans_rejects_variants():
    with pytest.raises(ValueError, match="use 'plans'"):
        describe_ingest_pipeline("plans:sheets")
