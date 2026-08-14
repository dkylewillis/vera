"""Command-line entry point for ``vera-lab``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from vera_lab.report import build_report
from vera_lab.run import coerce_pipeline_options


def pipeline_option(value: str) -> tuple[str, str]:
    """Parse ``KEY=VALUE`` pairs for ``--pipeline-option``."""
    if "=" not in value:
        raise argparse.ArgumentTypeError("must be KEY=VALUE")
    key, raw = value.split("=", 1)
    key = key.strip()
    if not key:
        raise argparse.ArgumentTypeError("option key must be non-empty")
    return key, raw


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vera-lab",
        description="Visualize ingest pipeline layout as a self-contained HTML report",
    )
    parser.add_argument(
        "source",
        help="Source PDF for a live pipeline run, or a .vera archive to inspect",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="vera-lab-report.html",
        help="Output HTML path (default: vera-lab-report.html)",
    )
    parser.add_argument(
        "--parser",
        action="append",
        dest="parsers",
        metavar="SPEC",
        help=(
            "Ingest pipeline spec (provider[:variant]). Repeat to compare. "
            "Ignored for .vera archives. Default: pymupdf"
        ),
    )
    parser.add_argument(
        "--pipeline-option",
        action="append",
        dest="pipeline_options",
        type=pipeline_option,
        default=[],
        metavar="KEY=VALUE",
        help="Provider-owned pipeline option (repeatable)",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=96,
        help="Page rasterization DPI (default: 96)",
    )
    parser.add_argument(
        "--pages",
        default=None,
        help="Page selection, e.g. 1-5,8 (default: first --max-pages pages)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=25,
        help="Maximum pages to rasterize (default: 25)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    source = Path(args.source)
    if not source.exists():
        parser.error(f"source not found: {source}")
    options = coerce_pipeline_options(args.pipeline_options)
    try:
        output = build_report(
            source,
            args.output,
            parsers=args.parsers,
            pipeline_options=options or None,
            dpi=args.dpi,
            pages=args.pages,
            max_pages=args.max_pages,
        )
    except Exception as exc:  # noqa: BLE001 - CLI surface
        print(f"vera-lab: {exc}", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
