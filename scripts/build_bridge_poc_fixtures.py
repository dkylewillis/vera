#!/usr/bin/env python3
"""Build approved + sibling fixture libraries for the Desktop bridge PoC demo."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / "tests"),
    str(ROOT / "packages" / "vera-doc" / "src"),
    str(ROOT / "packages" / "vera-ingest" / "src"),
    str(ROOT / "packages" / "vera-ingest-pymupdf" / "src"),
]

from helpers.pdfs import make_topic_pdf  # noqa: E402
from vera_doc import VeraDocument  # noqa: E402
from vera_ingest import convert  # noqa: E402


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "dev" / "fixtures" / "bridge-poc")
    approved = out / "approved"
    sibling = out / "sibling-unapproved"
    approved.mkdir(parents=True, exist_ok=True)
    sibling.mkdir(parents=True, exist_ok=True)

    pdf = approved / "detention-manual.pdf"
    make_topic_pdf(
        pdf,
        "Stormwater Detention",
        "Detention ponds must hold the 10-year storm when impervious area increases.",
    )
    pdf_archive = approved / "detention-manual.vera"
    convert(str(pdf), str(pdf_archive), model="hashing")

    md = approved / "notes.md"
    md.write_text(
        "# Field notes\n\n"
        "Pipe sizing for the outfall follows the municipal chart in section 4.2.\n"
        "company: GRID\n",
        encoding="utf-8",
    )
    md_archive = approved / "notes.vera"
    convert(
        str(md),
        str(md_archive),
        model="hashing",
        metadata={"company": "GRID"},
    )

    sentinel_pdf = sibling / "secret.pdf"
    make_topic_pdf(
        sentinel_pdf,
        "Confidential",
        "UNIQUE_SENTINEL_PHRASE_XYZ must never appear in approved-library answers.",
    )
    sentinel_archive = sibling / "secret.vera"
    convert(str(sentinel_pdf), str(sentinel_archive), model="hashing")

    frozen: dict[str, object] = {"model": "hashing", "archives": {}}
    for label, archive in (
        ("pdf", pdf_archive),
        ("markdown", md_archive),
        ("sentinel", sentinel_archive),
    ):
        with VeraDocument.open(archive) as doc:
            hits = doc.search(text="detention" if label != "sentinel" else "UNIQUE_SENTINEL", top_k=1)
            if not hits and label == "markdown":
                hits = doc.search(text="Pipe sizing", top_k=1)
            record = hits[0].record if hits else None
            frozen["archives"][label] = {
                "path": str(archive),
                "chunk_id": record.id if record else None,
                "text_preview": (record.text[:160] if record else None),
            }

    (out / "frozen-chunks.json").write_text(json.dumps(frozen, indent=2), encoding="utf-8")
    (out / "README.md").write_text(
        "# Bridge PoC fixtures\n\n"
        "- `approved/` — library root to grant in Desktop Bridge settings\n"
        "- `sibling-unapproved/` — must be denied (sentinel phrase)\n"
        "- `frozen-chunks.json` — expected chunk IDs after hashing convert\n",
        encoding="utf-8",
    )
    print(json.dumps({"ok": True, "root": str(out), "frozen": frozen}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
