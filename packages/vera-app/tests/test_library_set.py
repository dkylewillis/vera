from pathlib import Path

import pytest

from helpers.pdfs import make_topic_pdf
from vera_app.sidecar import handle
from vera_ingest import convert


def _library(root: Path, name: str, title: str, body: str) -> Path:
    root.mkdir(parents=True)
    pdf = root / f"{name}.pdf"
    make_topic_pdf(pdf, title, body)
    convert(str(pdf), str(root / f"{name}.vera"), model="hashing")
    return root


@pytest.fixture
def two_libraries(tmp_path):
    roads = _library(
        tmp_path / "roads",
        "roadway",
        "Roadway Design",
        "Our team delivered pavement drainage design for the roadway corridor.",
    )
    water = _library(
        tmp_path / "water",
        "treatment",
        "Water Treatment",
        "Our team designed drainage and pumping improvements for water treatment.",
    )
    built = handle({"id": "build", "action": "index_build", "path": str(roads), "recursive": True})
    assert built["ok"] is True
    return roads, water


def _search(request):
    response = handle({"id": "search", "action": "search", **request})
    assert response["ok"] is True, response.get("error")
    return response["result"]["results"]


def test_search_merges_results_from_every_library(two_libraries):
    roads, water = two_libraries
    results = _search(
        {
            "path": str(roads),
            "libraries": [
                {"path": str(roads), "recursive": True, "excludes": []},
                {"path": str(water), "recursive": True, "excludes": []},
            ],
            "query": "drainage design",
            "mode": "hybrid",
            "top_k": 10,
            "include_regions": True,
        }
    )
    files = {Path(result["file"]).parent for result in results}
    assert files == {roads, water}
    assert all(result.get("regions") for result in results)


def test_explicit_paths_take_precedence_over_libraries(two_libraries):
    roads, water = two_libraries
    only = str(water / "treatment.vera")
    results = _search(
        {
            "path": str(roads),
            "paths": [only],
            "libraries": [{"path": str(roads)}, {"path": str(water)}],
            "query": "drainage",
            "mode": "keyword",
            "top_k": 5,
        }
    )
    assert results
    assert {result["file"] for result in results} == {only}


def test_single_library_entry_keeps_the_library_path(two_libraries):
    roads, _ = two_libraries
    results = _search(
        {
            "path": str(roads),
            "libraries": [{"path": str(roads)}],
            "recursive": True,
            "query": "drainage",
            "mode": "keyword",
            "top_k": 5,
        }
    )
    assert results
    assert all(Path(result["file"]).parent == roads for result in results)
