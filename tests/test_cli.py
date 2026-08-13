import json
import subprocess
import sys
from pathlib import Path

import pytest
import vera_cli.commands as cli_commands
from test_convert_search import make_pdf
from vera_cli import str_to_bool
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
    assert info["file"] == str(out)
    assert Path(info["path"]).resolve() == out.resolve()

    report = run("validate", str(out), "--json")
    assert report["ok"] is True
    assert report["counts"]["chunks"] >= 2
    assert report["file"] == str(out)
    assert Path(report["path"]).resolve() == out.resolve()
    assert set(report["counts"]) >= {"chunks", "embeddings", "fts_rows", "attachments"}
    assert "documents" not in report["counts"]
    assert "assets" not in report["counts"]

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


def test_cli_parses_and_forwards_pipeline_options(tmp_path, monkeypatch):
    pdf = tmp_path / "scan.pdf"
    output = tmp_path / "scan.vera"
    pdf.write_bytes(b"%PDF-test-placeholder")
    captured = {}

    def fake_convert(input_path, output_path, **kwargs):
        captured.update(kwargs)
        return output_path

    monkeypatch.setattr(cli_commands, "convert", fake_convert)
    args = build_parser().parse_args(
        [
            "convert",
            str(pdf),
            str(output),
            "--chunk-size",
            "400",
            "--pipeline-option",
            "chunk_size=900",
            "--pipeline-option",
            "ocr_mode=force",
            "--pipeline-option",
            "custom_flag=true",
        ]
    )

    assert args.pipeline_options == [
        ("chunk_size", "900"),
        ("ocr_mode", "force"),
        ("custom_flag", "true"),
    ]
    assert args.func(args) == 0
    assert captured["chunk_size"] == 400
    assert captured["pipeline_options"] == {
        "chunk_size": 900,
        "ocr_mode": "force",
        "custom_flag": True,
    }


def test_cli_parses_and_forwards_ocr_allow_download(tmp_path, monkeypatch):
    pdf = tmp_path / "scan.pdf"
    output = tmp_path / "scan.vera"
    pdf.write_bytes(b"%PDF-test-placeholder")
    captured = {}

    def fake_convert(input_path, output_path, **kwargs):
        captured.update(kwargs)
        return output_path

    monkeypatch.setattr(cli_commands, "convert", fake_convert)
    args = build_parser().parse_args(
        ["convert", str(pdf), str(output), "--ocr-language", "fra", "--ocr-allow-download"]
    )

    assert args.ocr_allow_download is True
    assert args.func(args) == 0
    assert captured["ocr_download"] is True


def test_cli_ocr_allow_download_defaults_false():
    args = build_parser().parse_args(["convert", "scan.pdf"])
    assert args.ocr_allow_download is False


def test_cli_ocr_languages_list_json(capsys):
    args = build_parser().parse_args(["ocr-languages", "list", "eng+zzz", "--json"])
    assert args.func(args) == 0
    payload = json.loads(capsys.readouterr().out)
    codes = {entry["code"]: entry for entry in payload["languages"]}
    assert codes["eng"]["bundled"] is True
    assert codes["zzz"]["downloadable"] is False


def test_cli_ocr_languages_download_unknown_code_fails(capsys):
    args = build_parser().parse_args(["ocr-languages", "download", "zzz", "--json"])
    assert args.func(args) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "zzz" in payload["error"]


def test_cli_ocr_languages_download_forwards_to_helper(monkeypatch, capsys):
    calls = []

    def fake_download(language, *, progress=None, **kwargs):
        calls.append(language)
        return "/cache/dir"

    monkeypatch.setattr(cli_commands, "download_ocr_language_data", fake_download)
    args = build_parser().parse_args(["ocr-languages", "download", "fra", "--json"])

    assert args.func(args) == 0
    assert calls == ["fra"]
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"ok": True, "language": "fra", "downloaded": ["fra"], "cache_dir": "/cache/dir"}


def test_cli_default_ocr_language_is_not_forwarded_to_docling():
    pytest.importorskip("vera_ingest_docling")
    from vera_ingest import prepare_pipeline_options
    from vera_ingest_docling.options import DoclingOptions

    args = build_parser().parse_args(["convert", "scan.pdf", "--parser", "docling"])
    assert args.ocr_language == "eng"
    merged = prepare_pipeline_options(
        spec=args.parser,
        legacy_options={
            "chunk_size": args.chunk_size,
            "overlap": args.overlap,
            "ocr_mode": args.ocr_mode,
            "ocr_language": args.ocr_language,
            "ocr_dpi": args.ocr_dpi,
            "ocr_download": args.ocr_allow_download,
        },
    )
    assert "ocr_language" not in merged
    assert DoclingOptions.from_mapping(merged).ocr_language == "en"


def test_cli_rejects_non_positive_ocr_dpi():
    parser = build_parser()

    try:
        parser.parse_args(["convert", "scan.pdf", "--ocr-dpi", "0"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("non-positive OCR DPI should be rejected")


def test_cli_pipeline_option_strings_are_not_float_coerced(tmp_path, monkeypatch):
    pdf = tmp_path / "scan.pdf"
    output = tmp_path / "scan.vera"
    pdf.write_bytes(b"%PDF-test-placeholder")
    captured = {}

    def fake_convert(input_path, output_path, **kwargs):
        captured.update(kwargs)
        return output_path

    monkeypatch.setattr(cli_commands, "convert", fake_convert)
    args = build_parser().parse_args(
        [
            "convert",
            str(pdf),
            str(output),
            "--pipeline-option",
            "ocr_language=1.0",
            "--pipeline-option",
            "ocr_download=1",
            "--pipeline-option",
            "version=3.10",
            "--pipeline-option",
            "chunk_size=900",
        ]
    )

    assert args.func(args) == 0
    options = captured["pipeline_options"]
    assert options["ocr_language"] == "1.0"
    assert options["ocr_download"] == 1
    assert options["version"] == "3.10"
    assert options["chunk_size"] == 900

    from vera_ingest_pymupdf.options import PyMuPDFOptions

    parsed = PyMuPDFOptions.from_mapping(
        {
            "ocr_language": options["ocr_language"],
            "ocr_download": options["ocr_download"],
            "chunk_size": options["chunk_size"],
        }
    )
    assert parsed.ocr_language == "1.0"
    assert parsed.ocr_download is True
    assert parsed.chunk_size == 900


def test_cli_directory_convert_with_output_emits_json(tmp_path, capsys):
    args = build_parser().parse_args(
        ["convert", str(tmp_path), str(tmp_path / "out.vera"), "--json"]
    )
    assert args.func(args) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "output path" in payload["error"]


def test_cli_index_exclude_defaults_to_none():
    args = build_parser().parse_args(["index", "build", "library"])
    assert args.exclude is None


def test_str_to_bool_rejects_unknown_tokens():
    with pytest.raises(ValueError, match="invalid boolean"):
        str_to_bool("maybe")
    assert str_to_bool("false") is False
    assert str_to_bool("1") is True


def test_cli_rejects_unknown_store_original():
    parser = build_parser()
    try:
        parser.parse_args(["convert", "scan.pdf", "--store-original", "maybe"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("unknown store-original token should be rejected")


def test_cli_export_missing_source_matches_skill_error(tmp_path):
    pdf = tmp_path / "manual.pdf"
    out = tmp_path / "manual.vera"
    make_pdf(pdf)
    converted = subprocess.run(
        [
            sys.executable,
            "-m",
            "vera_cli",
            "convert",
            str(pdf),
            str(out),
            "--model",
            "hashing",
            "--store-original",
            "false",
            "--json",
        ],
        text=True,
        capture_output=True,
    )
    if converted.returncode != 0:
        raise AssertionError(converted.stderr)
    assert json.loads(converted.stdout)["ok"] is True

    exported = subprocess.run(
        [sys.executable, "-m", "vera_cli", "export", str(out), "--json"],
        text=True,
        capture_output=True,
    )
    payload = json.loads(exported.stdout)
    assert exported.returncode == 1
    assert payload == {
        "ok": False,
        "error": "Original source document is not stored in this archive",
    }


def test_export_rejects_unsafe_stored_filenames(tmp_path, monkeypatch):
    from vera import AttachmentRecord
    from vera_ingest import viewer as viewer_mod

    source = AttachmentRecord(
        id="src",
        data=b"%PDF-fake",
        media_type="application/pdf",
        filename="../evil.pdf",
    )
    monkeypatch.setattr(viewer_mod, "get_source_document", lambda document: source)
    with pytest.raises(ValueError, match="safe relative name"):
        viewer_mod.export_source_document(object(), str(tmp_path))

    source = AttachmentRecord(
        id="src",
        data=b"%PDF-fake",
        media_type="application/pdf",
        filename=str(tmp_path / "outside.pdf"),
    )
    monkeypatch.setattr(viewer_mod, "get_source_document", lambda document: source)
    with pytest.raises(ValueError, match="safe relative name"):
        viewer_mod.export_source_document(object(), str(tmp_path))
