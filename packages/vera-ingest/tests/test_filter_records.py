"""List chunks by record_type without ranking or loading embeddings."""

from __future__ import annotations

from vera_doc import ChunkRecord, VeraDocument
from vera_ingest.viewer import filter_records


def _archive(path, records: list[ChunkRecord]) -> None:
    with VeraDocument.create(path) as document:
        document.add(records)


def test_filter_lists_every_detail_in_a_folder(tmp_path):
    drainage = tmp_path / "drainage.vera"
    road = tmp_path / "road.vera"
    notes = tmp_path / "notes.vera"
    _archive(
        drainage,
        [
            ChunkRecord(
                id="chunk_0001",
                text="flume body that must not be returned",
                metadata={
                    "record_type": "detail",
                    "record_label": "CONCRETE FLUME",
                    "cd_description": "Concrete flume carrying runoff.",
                    "cd_sheet_number": "C-701",
                    "cd_detail_number": "4",
                    "cd_detail_type": "flume",
                    "source_filename": "drainage.pdf",
                    "page_start": 18,
                    "page_end": 18,
                    "heading_path": "C-701 > CONCRETE FLUME",
                    "regions": [
                        {
                            "kind": "page_bbox",
                            "page_number": 18,
                            "bbox": [120.0, 340.0, 980.0, 860.0],
                            "page_width": 2592.0,
                            "page_height": 1728.0,
                        }
                    ],
                },
            ),
            ChunkRecord(
                id="chunk_0002",
                text="title block",
                metadata={
                    "record_type": "sheet",
                    "record_label": "C-701",
                    "source_filename": "drainage.pdf",
                    "page_start": 18,
                },
            ),
        ],
    )
    _archive(
        road,
        [
            ChunkRecord(
                id="chunk_0009",
                text="curb body",
                metadata={
                    "record_type": "detail",
                    "record_label": "CURB",
                    "cd_description": "Concrete curb.",
                    "source_filename": "road.pdf",
                    "page_start": 2,
                    "regions": [{"kind": "page_bbox", "page_number": 2, "bbox": [0, 0, 10, 10]}],
                },
            )
        ],
    )
    _archive(notes, [ChunkRecord(id="chunk_0001", text="prose without a type")])
    (tmp_path / "bad.vera").write_text("not a database", encoding="utf-8")

    listed = filter_records(str(tmp_path), "detail")
    assert listed["record_type"] == "detail"
    assert listed["total"] == 2
    assert {row["label"] for row in listed["records"]} == {"CONCRETE FLUME", "CURB"}
    flume = next(row for row in listed["records"] if row["label"] == "CONCRETE FLUME")
    assert flume["file"].endswith("drainage.vera")
    assert flume["page_start"] == 18
    assert flume["description"] == "Concrete flume carrying runoff."
    assert flume["sheet_number"] == "C-701"
    assert flume["detail_number"] == "4"
    assert flume["detail_type"] == "flume"
    assert flume["regions"][0]["bbox"] == [120.0, 340.0, 980.0, 860.0]
    assert "text" not in flume
    assert "flume body" not in str(flume)
    assert any(item["file"].endswith("bad.vera") for item in listed["skipped_files"])

    types = {item["type"]: item["count"] for item in filter_records(str(tmp_path))["types"]}
    assert types == {"detail": 2, "sheet": 1}

    missing = filter_records(str(drainage), "profile")
    assert missing["records"] == []
    assert missing["total"] == 0
    assert {item["type"] for item in missing["types"]} == {"detail", "sheet"}
