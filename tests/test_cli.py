import json
import subprocess
import sys

import vera_cli.commands as cli_commands
from test_convert_search import make_pdf
from vera_cli.main import build_parser


def test_cli_convert_inspect_search(tmp_path):
    pdf = tmp_path / "manual.pdf"
    out = tmp_path / "manual.vera"
    make_pdf(pdf)

    convert_cmd = [sys.executable, "-m", "vera_cli", "convert", str(pdf), str(out), "--model", "hashing"]
    converted = subprocess.run(convert_cmd, text=True, capture_output=True, check=True)
    assert "Created" in converted.stdout

    inspected = subprocess.run(
        [sys.executable, "-m", "vera_cli", "inspect", str(out)],
        text=True,
        capture_output=True,
        check=True,
    )
    assert "Format: VERA v0.2" in inspected.stdout
    assert "Chunks:" in inspected.stdout

    searched = subprocess.run(
        [sys.executable, "-m", "vera_cli", "search", str(out), "restaurant parking", "--mode", "hybrid", "--top-k", "1"],
        text=True,
        capture_output=True,
        check=True,
    )
    assert "Score:" in searched.stdout
    assert "Page: 1" in searched.stdout
    assert "parking" in searched.stdout.lower()


def test_cli_json_output_for_agents(tmp_path):
    """Every command supports --json so agents can consume structured output."""
    pdf = tmp_path / "manual.pdf"
    out = tmp_path / "manual.vera"
    make_pdf(pdf)

    def run(*argv):
        proc = subprocess.run(
            [sys.executable, "-m", "vera_cli", *argv],
            text=True,
            capture_output=True,
            check=True,
        )
        return json.loads(proc.stdout)

    converted = run("convert", str(pdf), str(out), "--model", "hashing", "--json")
    assert converted["ok"] is True
    assert converted["output"].endswith("manual.vera")

    info = run("inspect", str(out), "--json")
    assert info["format_version"] == "0.2"
    assert info["pages"] == 2

    report = run("validate", str(out), "--json")
    assert report["ok"] is True
    assert report["counts"]["chunks"] >= 2

    payload = run("search", str(out), "restaurant parking", "--mode", "hybrid", "--top-k", "2", "--json", "--figures")
    assert payload["query"] == "restaurant parking"
    assert payload["results"]
    first = payload["results"][0]
    assert {"chunk_id", "score", "text", "page_start", "heading_path", "figures"} <= set(first)
    assert "parking" in first["text"].lower()
    assert "before_chunks" not in first
    assert "after_chunks" not in first

    with_context = run(
        "search",
        str(out),
        "restaurant parking",
        "--mode",
        "hybrid",
        "--top-k",
        "1",
        "--json",
        "--context-chunks",
        "1",
    )
    context_result = with_context["results"][0]
    assert {"before_chunks", "after_chunks"} <= set(context_result)
    assert isinstance(context_result["before_chunks"], list)
    assert isinstance(context_result["after_chunks"], list)

    invalid = subprocess.run(
        [sys.executable, "-m", "vera_cli", "search", str(out), "restaurant parking", "--context-chunks", "-1"],
        text=True,
        capture_output=True,
    )
    assert invalid.returncode != 0
    assert "non-negative" in invalid.stderr


def test_cli_batch_convert_directory_recursively(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    top_pdf = root / "top.pdf"
    nested_pdf = root / "nested" / "proposal.PDF"
    nested_pdf.parent.mkdir()
    make_pdf(top_pdf)
    make_pdf(nested_pdf)

    command = [
        sys.executable,
        "-m",
        "vera_cli",
        "convert",
        str(root),
        "--recursive",
        "--model",
        "hashing",
        "--json",
    ]
    converted = subprocess.run(command, text=True, capture_output=True, check=True)
    report = json.loads(converted.stdout)

    assert report["ok"] is True
    assert report["discovered"] == 2
    assert report["converted"] == 2
    assert report["skipped"] == 0
    assert (root / "top.vera").is_file()
    assert (nested_pdf.parent / "proposal.vera").is_file()

    repeated = subprocess.run(command, text=True, capture_output=True, check=True)
    repeated_report = json.loads(repeated.stdout)
    assert repeated_report["converted"] == 0
    assert repeated_report["skipped"] == 2


def test_cli_batch_convert_reports_malformed_existing_output(tmp_path):
    pdf = tmp_path / "manual.pdf"
    out = tmp_path / "manual.vera"
    make_pdf(pdf)
    out.write_bytes(b"not a sqlite database")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "vera_cli",
            "convert",
            str(tmp_path),
            "--model",
            "hashing",
            "--json",
        ],
        text=True,
        capture_output=True,
    )
    report = json.loads(result.stdout)

    assert result.returncode == 1
    assert report["ok"] is False
    assert report["skipped"] == 0
    assert report["malformed"] == 1
    assert report["malformed_existing"][0]["output"] == str(out)


def test_cli_parses_ocr_conversion_options():
    args = build_parser().parse_args(
        [
            "convert",
            "scan.pdf",
            "scan.vera",
            "--ocr",
            "force",
            "--ocr-language",
            "deu",
            "--ocr-dpi",
            "240",
        ]
    )

    assert args.ocr_mode == "force"
    assert args.ocr_language == "deu"
    assert args.ocr_dpi == 240


def test_cli_forwards_ocr_conversion_options(tmp_path, monkeypatch):
    pdf = tmp_path / "scan.pdf"
    output = tmp_path / "scan.vera"
    pdf.write_bytes(b"%PDF-test-placeholder")
    captured = {}

    def fake_convert(input_path, output_path, **kwargs):
        captured.update({"input": input_path, "output": output_path, **kwargs})
        return output_path

    monkeypatch.setattr(cli_commands, "convert", fake_convert)
    args = build_parser().parse_args(
        [
            "convert",
            str(pdf),
            str(output),
            "--ocr",
            "force",
            "--ocr-language",
            "deu",
            "--ocr-dpi",
            "240",
        ]
    )

    assert args.func(args) == 0
    assert captured["ocr_mode"] == "force"
    assert captured["ocr_language"] == "deu"
    assert captured["ocr_dpi"] == 240


def test_cli_rejects_non_positive_ocr_dpi():
    parser = build_parser()

    try:
        parser.parse_args(["convert", "scan.pdf", "--ocr-dpi", "0"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("non-positive OCR DPI should be rejected")
