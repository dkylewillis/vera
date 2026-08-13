from __future__ import annotations

import argparse

from .commands import (
    cmd_convert,
    cmd_eval,
    cmd_export,
    cmd_index_build,
    cmd_index_status,
    cmd_index_update,
    cmd_inspect,
    cmd_mcp,
    cmd_ocr_languages_download,
    cmd_ocr_languages_list,
    cmd_search,
    cmd_validate,
)


def non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def pipeline_option(value: str) -> tuple[str, str]:
    """Parse ``KEY=VALUE`` pairs for ``--pipeline-option`` / ``--embedder-option``."""
    if "=" not in value:
        raise argparse.ArgumentTypeError("must be KEY=VALUE")
    key, raw = value.split("=", 1)
    key = key.strip()
    if not key:
        raise argparse.ArgumentTypeError("option key must be non-empty")
    return key, raw


embedder_option = pipeline_option


def build_parser() -> argparse.ArgumentParser:
    """Build the ``vera`` command-line argument parser."""
    parser = argparse.ArgumentParser(prog="vera", description="Vector-Embedded Retrieval Archive CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    convert_p = sub.add_parser("convert", help="Convert a PDF or a directory of PDFs to VERA files")
    convert_p.add_argument("input", help="PDF file or directory containing PDFs")
    convert_p.add_argument("output", nargs="?", default=None, help="Output .vera path for a single PDF")
    convert_p.add_argument(
        "--model",
        default="hashing",
        help=(
            "Embedding model spec: provider:model-id "
            "(e.g. hashing, hashing:vera-hashing-384, "
            "sentence-transformers:all-MiniLM-L6-v2). "
            "Unknown providers exit with an error."
        ),
    )
    convert_p.add_argument(
        "--parser",
        default="pymupdf",
        help=(
            "Ingest pipeline spec: provider[:variant] "
            "(default pymupdf; optional docling or docling:hybrid when "
            "vera-ingest-docling is installed). Unknown providers exit with an error."
        ),
    )
    convert_p.add_argument(
        "--chunk-size",
        type=int,
        default=500,
        help=(
            "Compatibility alias for pipeline chunk_size (PyMuPDF: whitespace-split "
            "words; Docling: whitespace tokens)"
        ),
    )
    convert_p.add_argument(
        "--overlap",
        type=int,
        default=75,
        help=(
            "Compatibility alias for pipeline overlap (PyMuPDF: whitespace-split "
            "words; not forwarded to Docling)"
        ),
    )
    convert_p.add_argument("--store-original", default="true")
    convert_p.add_argument(
        "--ocr",
        dest="ocr_mode",
        choices=["auto", "off", "force"],
        default="auto",
        help="OCR mode: auto scans image-based pages, off disables OCR, force OCRs every page",
    )
    convert_p.add_argument(
        "--ocr-language",
        default="eng",
        help=(
            "Tesseract language code (PyMuPDF compatibility alias; not "
            "forwarded to Docling/RapidOCR)"
        ),
    )
    convert_p.add_argument("--ocr-dpi", type=positive_int, default=300, help="OCR render resolution (compatibility alias)")
    convert_p.add_argument(
        "--ocr-allow-download",
        action="store_true",
        help=(
            "Fetch missing --ocr-language Tesseract data from VERA's curated, "
            "checksum-verified registry and cache it locally (PyMuPDF only; "
            "compatibility alias). See 'vera ocr-languages list'."
        ),
    )
    convert_p.add_argument(
        "--pipeline-option",
        dest="pipeline_options",
        action="append",
        type=pipeline_option,
        default=[],
        metavar="KEY=VALUE",
        help=(
            "Provider-owned ingest option (repeatable). Overrides compatibility "
            "aliases for the same key when the selected pipeline accepts it."
        ),
    )
    convert_p.add_argument(
        "--embedder-option",
        dest="embedder_options",
        action="append",
        type=embedder_option,
        default=[],
        metavar="KEY=VALUE",
        help=(
            "Provider-owned embedding option (repeatable). Forwarded to the "
            "selected embedding provider (for example --embedder-option "
            "batch_size=64 or --embedder-option dimension=256)."
        ),
    )
    convert_p.add_argument("--recursive", action="store_true", help="Discover PDFs recursively when input is a directory")
    convert_p.add_argument("--overwrite", action="store_true", help="Overwrite existing .vera files during directory conversion")
    convert_p.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    convert_p.set_defaults(func=cmd_convert)

    inspect_p = sub.add_parser("inspect", help="Inspect a VERA file")
    inspect_p.add_argument("file")
    inspect_p.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    inspect_p.set_defaults(func=cmd_inspect)

    search_p = sub.add_parser("search", help="Search a VERA file, or a directory of VERA files as one corpus")
    search_p.add_argument("file", help="Path to a .vera file or a directory containing .vera files")
    search_p.add_argument("query")
    search_p.add_argument("--mode", choices=["semantic", "keyword", "hybrid"], default="hybrid")
    search_p.add_argument("--top-k", type=non_negative_int, default=10)
    search_p.add_argument(
        "--context-chunks",
        type=non_negative_int,
        default=0,
        help="Include N chunks before and after each search result in JSON output",
    )
    search_p.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    search_p.add_argument("--figures", action="store_true", help="Include figure metadata/captions in --json output")
    search_p.add_argument(
        "--recursive",
        action="store_true",
        help="Search nested .vera files when the target is an unindexed directory",
    )
    search_p.add_argument(
        "--exclude",
        action="append",
        default=None,
        help="Exclude a relative path or name pattern (repeatable)",
    )
    search_p.add_argument(
        "--regions",
        action="store_true",
        help="Include page/bbox highlight regions for each result in --json output",
    )
    search_p.set_defaults(func=cmd_search)

    index_p = sub.add_parser("index", help="Build and manage a local VERA library index")
    index_sub = index_p.add_subparsers(dest="index_command", required=True)

    index_build_p = index_sub.add_parser("build", help="Build a library index")
    index_build_p.add_argument("directory", help="Root directory containing .vera files")
    index_build_p.add_argument("--recursive", action="store_true", help="Discover .vera files recursively")
    index_build_p.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Exclude a relative path or name pattern (repeatable)",
    )
    index_build_p.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    index_build_p.set_defaults(func=cmd_index_build)

    index_update_p = index_sub.add_parser("update", help="Update an existing library index")
    index_update_p.add_argument("directory", help="Indexed library root")
    index_update_p.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    index_update_p.set_defaults(func=cmd_index_update)

    index_status_p = index_sub.add_parser("status", help="Show library index freshness")
    index_status_p.add_argument("directory", help="Indexed library root")
    index_status_p.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    index_status_p.set_defaults(func=cmd_index_status)

    validate_p = sub.add_parser("validate", help="Validate a VERA file")
    validate_p.add_argument("file")
    validate_p.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    validate_p.set_defaults(func=cmd_validate)

    export_p = sub.add_parser("export", help="Export the original source document from a VERA file")
    export_p.add_argument("file")
    export_p.add_argument("output", nargs="?", default=None, help="Output path or directory (default: stored filename)")
    export_p.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    export_p.set_defaults(func=cmd_export)

    mcp_p = sub.add_parser("mcp", help="Run the MCP server (stdio) exposing VERA tools to AI agents")
    mcp_p.set_defaults(func=cmd_mcp)

    ocr_languages_p = sub.add_parser(
        "ocr-languages",
        help="List or download Tesseract OCR language data used by the pymupdf parser",
    )
    ocr_languages_sub = ocr_languages_p.add_subparsers(dest="ocr_languages_command", required=True)

    ocr_languages_list_p = ocr_languages_sub.add_parser(
        "list", help="List bundled, cached, and downloadable OCR language codes"
    )
    ocr_languages_list_p.add_argument(
        "language",
        nargs="?",
        default=None,
        help="Limit to specific '+'-joined codes (e.g. eng+fra); defaults to every known code",
    )
    ocr_languages_list_p.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    ocr_languages_list_p.set_defaults(func=cmd_ocr_languages_list)

    ocr_languages_download_p = ocr_languages_sub.add_parser(
        "download", help="Download one or more Tesseract language codes into the local cache"
    )
    ocr_languages_download_p.add_argument(
        "language", help="'+'-joined Tesseract language code(s) to fetch, e.g. fra or fra+deu"
    )
    ocr_languages_download_p.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    ocr_languages_download_p.set_defaults(func=cmd_ocr_languages_download)

    eval_p = sub.add_parser("eval", help="Evaluate retrieval quality against a query file")
    eval_p.add_argument("file")
    eval_p.add_argument("queries", help="JSON or YAML file with query cases")
    eval_p.add_argument("--mode", choices=["semantic", "keyword", "hybrid", "all"], default="all")
    eval_p.add_argument("--top-k", type=non_negative_int, default=5)
    eval_p.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    eval_p.set_defaults(func=cmd_eval)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the ``vera`` CLI and return a process exit code.

    Args:
        argv: Optional argument list. Defaults to ``sys.argv[1:]``.

    Returns:
        Integer exit code (0 on success).
    """
    args = build_parser().parse_args(argv)
    return args.func(args)
