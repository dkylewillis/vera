"""Offline checks for convert timing lines."""

from __future__ import annotations

from vera_ingest.timing import format_timing_line, log_event, timed_step


def test_format_timing_line_includes_step_and_elapsed_ms():
    line = format_timing_line("import_docling", 12450, ready=True)
    assert "timing step=import_docling" in line
    assert "elapsed_ms=12450" in line
    assert "ready=True" in line
    assert line.endswith("ready=True") or " ready=" in line


def test_format_timing_line_omits_empty_fields():
    line = format_timing_line("sidecar_start", reason=None, parser="")
    assert "elapsed_ms=" not in line
    assert "reason=" not in line
    assert "parser=" not in line


def test_timed_step_records_elapsed_and_extra_fields(capsys):
    with timed_step("resolve_embedder", model="hashing") as extras:
        extras["downloaded"] = False
        extras["model"] = "hashing:vera-hashing-384"
    err = capsys.readouterr().err
    lines = [line for line in err.splitlines() if "timing step=resolve_embedder" in line]
    assert len(lines) == 2
    assert "elapsed_ms=" not in lines[0]
    assert "elapsed_ms=" in lines[1]
    assert "model=hashing:vera-hashing-384" in lines[1]
    assert "downloaded=False" in lines[1]


def test_log_event_writes_stderr(capsys):
    log_event("sidecar_start")
    err = capsys.readouterr().err
    assert "timing step=sidecar_start" in err
