"""List chunks by metadata without ranking or loading embeddings."""

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

    listed = filter_records(str(tmp_path), {"record_type": "detail", "cd_sheet_number": "C-701"})
    assert listed["where"] == {"record_type": "detail", "cd_sheet_number": "C-701"}
    assert listed["total"] == 1
    flume = listed["records"][0]
    assert flume["metadata"]["record_label"] == "CONCRETE FLUME"
    assert flume["file"].endswith("drainage.vera")
    assert flume["page_start"] == 18
    assert flume["metadata"]["cd_description"] == "Concrete flume carrying runoff."
    assert flume["metadata"]["cd_sheet_number"] == "C-701"
    assert flume["metadata"]["cd_detail_number"] == "4"
    assert flume["metadata"]["cd_detail_type"] == "flume"
    assert flume["regions"][0]["bbox"] == [120.0, 340.0, 980.0, 860.0]
    assert "text" not in flume
    assert "flume body" not in str(flume)
    assert any(item["file"].endswith("bad.vera") for item in listed["skipped_files"])

    both = filter_records(str(tmp_path), {"cd_detail_type": ["flume", "curb"]})
    assert both["total"] == 1
    assert both["records"][0]["metadata"]["record_label"] == "CONCRETE FLUME"

    details = filter_records(str(tmp_path), {"record_type": "detail"})
    assert details["total"] == 2
    assert {row["metadata"]["record_label"] for row in details["records"]} == {
        "CONCRETE FLUME",
        "CURB",
    }

    keys = {item["key"]: item for item in filter_records(str(tmp_path))["facets"]}
    assert keys["record_type"]["count"] == 3
    assert keys["record_type"]["values"] == [
        {"value": "detail", "count": 2},
        {"value": "sheet", "count": 1},
    ]
    assert keys["cd_detail_type"]["count"] == 1
    assert "page_start" not in keys
    assert "records" not in filter_records(str(tmp_path))

    missing = filter_records(str(drainage), {"record_type": "profile"})
    assert missing["records"] == []
    assert missing["total"] == 0
    assert {item["key"] for item in missing["facets"]} >= {"record_type", "record_label"}


def test_filter_omits_values_when_a_facet_is_large(tmp_path):
    from vera_ingest.viewer import _FACET_VALUE_LIMIT

    path = tmp_path / "many.vera"
    records = [
        ChunkRecord(
            id=f"chunk_{index:04d}",
            text=f"label {index}",
            metadata={"record_type": "detail", "record_label": f"LABEL {index}"},
        )
        for index in range(_FACET_VALUE_LIMIT + 1)
    ]
    _archive(path, records)
    facets = {item["key"]: item for item in filter_records(str(path))["facets"]}
    assert facets["record_type"]["values"] == [{"value": "detail", "count": _FACET_VALUE_LIMIT + 1}]
    assert facets["record_label"]["distinct"] == _FACET_VALUE_LIMIT + 1
    assert "values" not in facets["record_label"]
