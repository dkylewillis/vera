"""Convert() emits timed stderr steps without logging PDF text."""

from helpers.pdfs import make_pdf
from vera_ingest import convert


def test_convert_emits_timed_steps(tmp_path, capsys):
    pdf = tmp_path / "ordinance.pdf"
    out = tmp_path / "ordinance.vera"
    make_pdf(pdf)

    convert(str(pdf), str(out), model="hashing", chunk_size=100, overlap=0)

    err = capsys.readouterr().err
    for step in ("resolve_pipeline", "resolve_embedder", "ingest", "embed", "write_archive"):
        assert f"timing step={step}" in err
    assert err.count("elapsed_ms=") >= 5
    assert "one parking space" not in err
    assert "impervious area" not in err
