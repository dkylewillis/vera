"""Emit a self-contained HTML layout report."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

from vera_lab.archive import load_archive_document
from vera_lab.lint import lint_document
from vera_lab.model import LabDocument
from vera_lab.render import parse_page_selection, rasterize_pages, validate_pages_arg
from vera_lab.run import load_live_document
from vera_lab.stats import compute_stats


def build_report(
    source: str | Path,
    output: str | Path,
    *,
    parsers: list[str] | None = None,
    pipeline_options: dict[str, Any] | None = None,
    dpi: int = 96,
    pages: str | None = None,
    max_pages: int = 25,
) -> str:
    """Build a self-contained HTML report and return the output path."""
    source_path = Path(source)
    output_path = Path(output)
    pages_arg = validate_pages_arg(pages)
    runs = _load_runs(source_path, parsers=parsers, pipeline_options=pipeline_options)
    if not runs:
        raise ValueError("No lab documents were produced")

    primary = runs[0]["document"]
    page_count = len(primary.pages) or _pdf_page_count(primary.source_bytes)
    selected_pages, omitted = parse_page_selection(
        pages_arg,
        max_pages=max_pages,
        page_count=page_count,
    )
    for run in runs:
        document: LabDocument = run["document"]
        run["rendered_pages"] = {
            str(page_number): payload
            for page_number, payload in rasterize_pages(
                document.source_bytes,
                selected_pages,
                dpi=dpi,
            ).items()
        }
        # Drop raw bytes from the JSON payload (images are already data URLs).
        payload_doc = document.as_dict()
        run["document"] = payload_doc
        run["issues"] = [issue.as_dict() for issue in run["issues"]]
        run["stats"] = run["stats"]

    payload = {
        "selected_pages": selected_pages,
        "pages_omitted": omitted,
        "pages_omitted_message": (
            f"Showing {len(selected_pages)} of {page_count} pages "
            f"(dpi={dpi}, max_pages={max_pages})."
            if omitted
            else None
        ),
        "dpi": dpi,
        "runs": runs,
    }
    html = _render_html(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return str(output_path)


def _load_runs(
    source_path: Path,
    *,
    parsers: list[str] | None,
    pipeline_options: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if source_path.suffix.lower() == ".vera":
        document = load_archive_document(source_path)
        return [
            {
                "label": document.parser_name or "archive",
                "document": document,
                "issues": lint_document(document),
                "stats": compute_stats(document),
            }
        ]

    specs = parsers or ["pymupdf"]
    # Preserve order while de-duplicating.
    ordered: list[str] = []
    for spec in specs:
        if spec not in ordered:
            ordered.append(spec)
    runs: list[dict[str, Any]] = []
    for spec in ordered:
        document = load_live_document(
            source_path,
            parser=spec,
            pipeline_options=pipeline_options,
        )
        runs.append(
            {
                "label": spec,
                "document": document,
                "issues": lint_document(document),
                "stats": compute_stats(document),
            }
        )
    return runs


def _pdf_page_count(source_bytes: bytes) -> int:
    import pymupdf as fitz

    document = fitz.open(stream=source_bytes, filetype="pdf")
    try:
        return int(document.page_count)
    finally:
        document.close()


def _asset_text(name: str) -> str:
    return resources.files("vera_lab.assets").joinpath(name).read_text(encoding="utf-8")


def _render_html(payload: dict[str, Any]) -> str:
    css = _asset_text("report.css")
    js = _asset_text("report.js")
    data_json = json.dumps(payload, ensure_ascii=False)
    # Guard against </script> in JSON text.
    data_json = data_json.replace("<", "\\u003c")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>vera-lab</title>
  <style>
{css}
  </style>
</head>
<body>
  <header class="app-header">
    <div>
      <h1 id="title">vera-lab</h1>
      <div class="meta" id="subtitle"></div>
    </div>
    <div class="controls">
      <div class="parser-switch" id="parser-switch"></div>
      <label><input type="checkbox" data-layer="blocks" checked /> Blocks</label>
      <label><input type="checkbox" data-layer="chunks" checked /> Chunks</label>
      <label><input type="checkbox" data-layer="figures" checked /> Figures</label>
    </div>
  </header>
  <div class="layout">
    <main class="pages" id="pages"></main>
    <aside class="sidebar">
      <section>
        <h3>Compare</h3>
        <div id="compare"></div>
      </section>
      <section>
        <h3>Stats</h3>
        <div id="stats"></div>
      </section>
      <section>
        <h3>Issues</h3>
        <div id="issues"></div>
      </section>
      <section>
        <h3>Detail</h3>
        <div class="detail" id="detail">Select a block, chunk, or figure.</div>
      </section>
      <section>
        <h3>Blocks</h3>
        <div class="list" id="block-list"></div>
      </section>
      <section>
        <h3>Chunks</h3>
        <div class="list" id="chunk-list"></div>
      </section>
      <section>
        <h3>Figures</h3>
        <div class="list" id="figure-list"></div>
      </section>
    </aside>
  </div>
  <script>
window.__VERA_LAB__ = {data_json};
{js}
  </script>
</body>
</html>
"""
