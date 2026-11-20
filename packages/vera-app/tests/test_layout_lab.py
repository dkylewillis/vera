"""Desktop layout-lab handler."""

from pathlib import Path

from helpers.pdfs import make_pdf
from vera_app.layout_lab import layout_report_destination, layout_report_filename
from vera_app.sidecar import handle
from vera_ingest import convert


def test_layout_report_filename_keeps_the_source_name():
    assert layout_report_filename(Path("manual.pdf.vera")) == "manual.pdf.lab.html"
    assert layout_report_filename(Path("notes.VERA")) == "notes.lab.html"


def test_layout_report_destination_keeps_same_names_apart(tmp_path: Path):
    output_dir = tmp_path / "reports"
    north = tmp_path / "Plans" / "North" / "Site.pdf.vera"
    south = tmp_path / "Plans" / "South" / "Site.pdf.vera"
    first = layout_report_destination(north, output_dir)
    second = layout_report_destination(south, output_dir)
    assert first.name == second.name == "Site.pdf.lab.html"
    assert first != second
    assert output_dir.resolve() in first.resolve().parents
    assert output_dir.resolve() in second.resolve().parents
    assert "North" in first.parts
    assert "South" in second.parts


def test_layout_lab_requires_a_folder(tmp_path: Path):
    archive = tmp_path / "notes.vera"
    archive.write_bytes(b"not an archive")
    response = handle({"action": "layout_lab", "path": str(archive), "output_dir": "  "})
    assert response["ok"] is False
    assert "Settings" in response["error"]


def test_layout_lab_rejects_a_source_file(tmp_path: Path):
    pdf = tmp_path / "notes.pdf"
    make_pdf(pdf)
    response = handle({
        "action": "layout_lab",
        "path": str(pdf),
        "output_dir": str(tmp_path / "reports"),
    })
    assert response["ok"] is False
    assert ".vera" in response["error"]


def test_layout_lab_writes_an_html_report(tmp_path: Path):
    pdf = tmp_path / "notes.pdf"
    make_pdf(pdf)
    archive = tmp_path / "notes.pdf.vera"
    convert(str(pdf), str(archive), model="hashing")
    output_dir = tmp_path / "reports"
    response = handle({
        "action": "layout_lab",
        "path": str(archive),
        "output_dir": str(output_dir),
    })
    assert response["ok"] is True
    result = response["result"]
    written = Path(result["path"])
    assert written == layout_report_destination(archive, output_dir)
    assert written.name == "notes.pdf.lab.html"
    assert written.is_file()
    assert output_dir.resolve() in written.resolve().parents
    assert result["pages"] == 2
    assert result["pages_omitted"] is False
    html = written.read_text(encoding="utf-8")
    assert "<html" in html.lower()
