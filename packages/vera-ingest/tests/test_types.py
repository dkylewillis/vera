"""Tests for shared ingest types and ParsedBlock → IngestBlock conversion."""

from vera_ingest.chunking import build_chunks_from_blocks
from vera_ingest.types import IngestBlock, ParsedBlock


def test_ingest_block_from_parsed_copies_layout_fields():
    parsed = ParsedBlock(
        page_number=3,
        block_type="paragraph",
        text="Detention volume requirements.",
        bbox=(72.0, 100.0, 400.0, 140.0),
        heading_level=None,
        image_bytes=None,
        image_ext="",
    )
    block = IngestBlock.from_parsed("block_000003", parsed)

    assert block.block_id == "block_000003"
    assert block.page_number == 3
    assert block.block_type == "paragraph"
    assert block.text == "Detention volume requirements."
    assert block.bbox == (72.0, 100.0, 400.0, 140.0)
    assert block.heading_level is None
    assert block.image_bytes is None
    assert block.image_ext == ""
    assert block.regions == []


def test_ingest_block_from_parsed_accepts_regions():
    parsed = ParsedBlock(1, "image", "", image_bytes=b"png", image_ext="png")
    regions = [{"page_number": 1, "bbox": [0, 0, 10, 10]}]
    block = IngestBlock.from_parsed("img_1", parsed, regions=regions)
    assert block.image_bytes == b"png"
    assert block.image_ext == "png"
    assert block.regions == regions
    assert block.regions is not regions


def test_build_chunks_from_blocks_accepts_ingest_block():
    parsed = ParsedBlock(1, "paragraph", "Parking spaces are required for restaurants.")
    ingest = IngestBlock.from_parsed("b1", parsed)
    from_parsed = build_chunks_from_blocks([("b1", parsed)])
    from_ingest = build_chunks_from_blocks([("b1", ingest)])
    assert len(from_parsed) == 1
    assert from_parsed[0].text == from_ingest[0].text
    assert from_ingest[0].block_ids == ["b1"]
