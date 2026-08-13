import hashlib
from pathlib import Path

import pytest

from vera import VeraDocument
from vera_ingest import batch_convert, convert
from vera_ingest.viewer import regions_for
from vera_ingest_pymupdf import parser as pdf_parser
from vera_ingest_pymupdf.tessdata_manager import ensure_language_data


def _scan_pixmap(text: str | None = None):
    import fitz

    if text is None:
        pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 600, 800), False)
        pixmap.clear_with(255)
        return pixmap

    source = fitz.open()
    page = source.new_page(width=600, height=800)
    page.insert_text((60, 100), text, fontsize=22)
    pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    source.close()
    return pixmap


def make_scanned_pdf(
    path,
    *,
    native_first_page: bool = False,
    rendered_text: str | None = None,
    native_header: str | None = None,
):
    import fitz

    doc = fitz.open()
    if native_first_page:
        native = doc.new_page(width=600, height=800)
        native.insert_text(
            (60, 100),
            "Native introduction with enough searchable characters to bypass optical recognition.",
        )
    page = doc.new_page(width=600, height=800)
    pixmap = _scan_pixmap(rendered_text)
    page.insert_image(page.rect, stream=pixmap.tobytes("png"))
    if native_header:
        page.insert_text((40, 24), native_header, fontsize=10)
    doc.save(path)
    doc.close()


def _recognized_content(text: str = "Recognized scanned stormwater requirements"):
    return (
        text,
        {
            "blocks": [
                {
                    "type": 0,
                    "bbox": (48.0, 72.0, 520.0, 112.0),
                    "lines": [
                        {
                            "dir": (1.0, 0.0),
                            "spans": [
                                {
                                    "text": text,
                                    "bbox": (48.0, 72.0, 520.0, 112.0),
                                    "size": 12.0,
                                    "flags": 0,
                                }
                            ],
                        }
                    ],
                }
            ]
        },
    )


def test_auto_ocr_processes_only_scanned_pages_and_preserves_regions(tmp_path, monkeypatch):
    pdf = tmp_path / "mixed.pdf"
    make_scanned_pdf(pdf, native_first_page=True)
    calls = []

    def fake_ocr(page, *, language, dpi, allow_download=False):
        calls.append((page.number + 1, language, dpi))
        return _recognized_content()

    monkeypatch.setattr(pdf_parser, "_ocr_page_content", fake_ocr)
    diagnostics = {}

    pages, blocks = pdf_parser.parse_pdf_structured(
        str(pdf),
        ocr_mode="auto",
        ocr_language="eng",
        ocr_dpi=300,
        diagnostics=diagnostics,
    )

    assert calls == [(2, "eng", 300)]
    assert diagnostics["ocr_pages"] == [2]
    assert "Native introduction" in pages[0].text
    assert pages[1].text == "Recognized scanned stormwater requirements"
    recognized = next(block for block in blocks if block.text.startswith("Recognized"))
    assert recognized.page_number == 2
    assert recognized.bbox == (48.0, 72.0, 520.0, 112.0)
    assert any(block.block_type == "image" and block.page_number == 2 for block in blocks)


_NATIVE_SCAN_HEADER = "CONFIDENTIAL Bates ABC-2024-001234"


def test_page_needs_ocr_when_native_header_sits_on_large_image():
    layout = {"blocks": [{"type": 1, "bbox": (0.0, 0.0, 600.0, 800.0)}]}
    assert sum(character.isalnum() for character in _NATIVE_SCAN_HEADER) >= 10
    assert pdf_parser._page_needs_ocr(_NATIVE_SCAN_HEADER, layout, width=600, height=800)
    assert not pdf_parser._page_needs_ocr("x" * 250, layout, width=600, height=800)
    assert not pdf_parser._page_needs_ocr("", {"blocks": []}, width=600, height=800)


def test_auto_ocr_processes_scan_with_native_header(tmp_path, monkeypatch):
    pdf = tmp_path / "header-scan.pdf"
    make_scanned_pdf(pdf, native_header=_NATIVE_SCAN_HEADER)
    calls = []

    def fake_ocr(page, *, language, dpi, allow_download=False):
        calls.append(page.number + 1)
        return _recognized_content()

    monkeypatch.setattr(pdf_parser, "_ocr_page_content", fake_ocr)
    diagnostics = {}

    pages, _blocks = pdf_parser.parse_pdf_structured(
        str(pdf),
        ocr_mode="auto",
        diagnostics=diagnostics,
    )

    assert calls == [1]
    assert diagnostics["ocr_pages"] == [1]
    assert pages[0].text == "Recognized scanned stormwater requirements"


def test_path_like_ocr_language_is_rejected(tmp_path):
    pdf = tmp_path / "scan.pdf"
    make_scanned_pdf(pdf)

    with pytest.raises(ValueError, match="Invalid OCR language"):
        pdf_parser.parse_pdf_structured(str(pdf), ocr_language="../tessdata/eng")


def test_ocr_off_skips_scanned_page(tmp_path, monkeypatch):
    pdf = tmp_path / "scan.pdf"
    make_scanned_pdf(pdf)
    monkeypatch.setattr(
        pdf_parser,
        "_ocr_page_content",
        lambda *_args, **_kwargs: pytest.fail("OCR should be disabled"),
    )

    pages, blocks = pdf_parser.parse_pdf_structured(str(pdf), ocr_mode="off")

    assert pages[0].text == ""
    assert not any(block.text for block in blocks)


def test_force_ocr_processes_native_text_page(tmp_path, monkeypatch):
    from test_convert_search import make_pdf

    pdf = tmp_path / "native.pdf"
    make_pdf(pdf)
    calls = []

    def fake_ocr(page, *, language, dpi, allow_download=False):
        calls.append(page.number + 1)
        return _recognized_content(f"Forced OCR page {page.number + 1}")

    monkeypatch.setattr(pdf_parser, "_ocr_page_content", fake_ocr)
    diagnostics = {}

    pages, _blocks = pdf_parser.parse_pdf_structured(
        str(pdf),
        ocr_mode="force",
        diagnostics=diagnostics,
    )

    assert calls == [1, 2]
    assert [page.text for page in pages] == ["Forced OCR page 1", "Forced OCR page 2"]
    assert diagnostics["ocr_pages"] == [1, 2]


def test_ocr_honors_cancellation_immediately_after_page_returns(tmp_path, monkeypatch):
    pdf = tmp_path / "scan.pdf"
    make_scanned_pdf(pdf)

    class Token:
        cancelled = False

        def raise_if_interrupted(self):
            if self.cancelled:
                raise RuntimeError("Conversion cancelled")

    cancel = Token()

    def fake_ocr(_page, *, language, dpi, allow_download=False):
        cancel.cancelled = True
        return _recognized_content()

    monkeypatch.setattr(pdf_parser, "_ocr_page_content", fake_ocr)

    with pytest.raises(RuntimeError, match="Conversion cancelled"):
        pdf_parser.parse_pdf_structured(str(pdf), ocr_mode="force", cancel=cancel)


def test_convert_records_ocr_metadata_and_searchable_regions(tmp_path, monkeypatch):
    pdf = tmp_path / "scan.pdf"
    out = tmp_path / "scan.vera"
    make_scanned_pdf(pdf)
    monkeypatch.setattr(
        pdf_parser,
        "_ocr_page_content",
        lambda _page, *, language, dpi, allow_download=False: _recognized_content(),
    )

    convert(
        str(pdf),
        str(out),
        model="hashing",
        ocr_mode="auto",
        ocr_language="eng",
        ocr_dpi=300,
    )

    document = VeraDocument.open(str(out))
    try:
        ocr = document.inspect()["ocr"]
        assert ocr["ocr_engine"] == "tesseract"
        assert ocr["ocr_mode"] == "auto"
        assert ocr["ocr_language"] == "eng"
        assert ocr["ocr_dpi"] == 300
        assert ocr["ocr_pages"] == [1]
        result = document.search("scanned stormwater", mode="keyword", top_k=1)[0]
        assert result.page_start == 1
        assert regions_for(document, result)[0]["bbox"] == [48.0, 72.0, 520.0, 112.0]
    finally:
        document.close()


def test_bundled_english_tessdata_is_available_and_pinned():
    tessdata = ensure_language_data("eng", allow_download=False)

    assert tessdata is not None
    data = (Path(tessdata) / "eng.traineddata").read_bytes()
    assert hashlib.sha256(data).hexdigest() == (
        "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2"
    )


def test_ocr_error_explains_unbundled_language_requirement():
    class BrokenPage:
        number = 0

        def get_textpage_ocr(self, **_kwargs):
            raise RuntimeError("No OCR support")

    with pytest.raises(RuntimeError, match="TESSDATA_PREFIX"):
        pdf_parser._ocr_page_content(BrokenPage(), language="fra", dpi=300)


def test_empty_ocr_output_is_not_published(tmp_path, monkeypatch):
    pdf = tmp_path / "scan.pdf"
    out = tmp_path / "scan.vera"
    make_scanned_pdf(pdf)
    monkeypatch.setattr(
        pdf_parser,
        "_ocr_page_content",
        lambda _page, *, language, dpi, allow_download=False: ("", {"blocks": []}),
    )

    with pytest.raises(ValueError, match="No searchable text"):
        convert(str(pdf), str(out), model="hashing")

    assert not out.exists()


def test_batch_reports_ocr_failures_and_continues(tmp_path, monkeypatch):
    scanned = tmp_path / "scan.pdf"
    make_scanned_pdf(scanned)

    def failed_ocr(_page, *, language, dpi, allow_download=False):
        raise RuntimeError(f"missing OCR language data: {language}")

    monkeypatch.setattr(pdf_parser, "_ocr_page_content", failed_ocr)

    report = batch_convert(
        str(tmp_path),
        model="hashing",
        ocr_language="fra",
        ocr_dpi=240,
    )

    assert report["failed"] == 1
    assert report["converted"] == 0
    assert report["errors"][0]["input"] == str(scanned)
    assert "missing OCR language data: fra" in report["errors"][0]["error"]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"ocr_mode": "sometimes"}, "ocr_mode"),
        ({"ocr_language": " "}, "ocr_language"),
        ({"ocr_dpi": 0}, "ocr_dpi"),
    ],
)
def test_ocr_options_are_validated(tmp_path, kwargs, message):
    pdf = tmp_path / "scan.pdf"
    make_scanned_pdf(pdf)

    with pytest.raises(ValueError, match=message):
        pdf_parser.parse_pdf_structured(str(pdf), **kwargs)


def test_real_tesseract_smoke(tmp_path):
    pdf = tmp_path / "real-scan.pdf"
    make_scanned_pdf(pdf, rendered_text="VERA optical recognition smoke test")

    pages, blocks = pdf_parser.parse_pdf_structured(str(pdf), ocr_mode="force")

    assert "VERA" in pages[0].text
    assert any("VERA" in block.text for block in blocks)
