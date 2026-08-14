import importlib
import io
import json
import queue
import threading
from pathlib import Path

import pytest

from helpers.pdfs import make_pdf, make_structured_pdf, make_topic_pdf
from vera_app.cancellation import CancellationToken
from vera_app.llm import (
    ChatResponse,
    LlmConfig,
    ProviderHttpError,
    ToolCall,
    ToolsUnsupportedError,
    VisionUnsupportedError,
)
from vera_app.sidecar import handle
from vera_ingest import convert


def _llm_payload():
    return {
        "provider": "openai_compatible",
        "model": "test-model",
        "base_url": "http://localhost:1234/v1",
    }


class _ScriptedStdin:
    """stdin stand-in that lets tests push lines after a request is in flight."""

    def __init__(self):
        self._lines: queue.Queue[str | None] = queue.Queue()

    def push(self, line: str | None) -> None:
        self._lines.put(line)

    def __iter__(self):
        return self

    def __next__(self) -> str:
        line = self._lines.get()
        if line is None:
            raise StopIteration
        return line


@pytest.fixture
def nested_app_library(tmp_path):
    root = tmp_path / "proposals"
    roadway = root / "transportation" / "roadway.vera"
    roadway.parent.mkdir(parents=True)
    roadway_pdf = roadway.with_suffix(".pdf")
    make_topic_pdf(
        roadway_pdf,
        "Roadway Design",
        "Our team delivered roadway corridor design and construction administration.",
    )
    convert(str(roadway_pdf), str(roadway), model="hashing")

    water = root / "utilities" / "water.vera"
    water.parent.mkdir(parents=True)
    water_pdf = water.with_suffix(".pdf")
    make_topic_pdf(
        water_pdf,
        "Water Treatment",
        "Our team designed municipal water treatment and pumping improvements.",
    )
    convert(str(water_pdf), str(water), model="hashing")
    return root


def test_index_actions_and_recursive_folder_search(nested_app_library):
    missing = handle(
        {
            "id": "status-missing",
            "action": "index_status",
            "path": str(nested_app_library),
            "verify_hashes": False,
        }
    )
    assert missing["ok"] is True
    assert missing["result"]["exists"] is False

    inspected = handle(
        {
            "id": "inspect-recursive",
            "action": "inspect",
            "path": str(nested_app_library),
            "recursive": True,
        }
    )
    assert inspected["ok"] is True
    assert inspected["result"]["file_count"] == 2

    fallback = handle(
        {
            "id": "search-recursive",
            "action": "search",
            "path": str(nested_app_library),
            "paths": [str(nested_app_library)],
            "recursive": True,
            "query": "water treatment pumping",
            "top_k": 1,
        }
    )
    assert fallback["ok"] is True
    assert fallback["result"][0]["file"].endswith("water.vera")

    built = handle(
        {
            "id": "index-build",
            "action": "index_build",
            "path": str(nested_app_library),
            "recursive": True,
            "excludes": ["archive"],
        }
    )
    assert built["ok"] is True
    assert built["result"]["indexed"] == 2

    fresh = handle(
        {
            "id": "status-fresh",
            "action": "index_status",
            "path": str(nested_app_library),
        }
    )
    assert fresh["ok"] is True
    assert fresh["result"]["fresh"] is True
    assert fresh["result"]["recursive"] is True
    assert fresh["result"]["generation_id"].startswith("generation-")
    assert fresh["result"]["verified_at"] == fresh["result"]["checked_at"]
    assert fresh["result"]["model_groups"][0]["documents"] == 2
    assert fresh["result"]["index_size_bytes"] > 0

    summary = handle(
        {
            "id": "inspect-summary",
            "action": "inspect",
            "path": str(nested_app_library),
            "summary_only": True,
            "default_recursive": True,
        }
    )
    assert summary["ok"] is True
    assert summary["result"]["summary_source"] == "index"
    assert summary["result"]["summary_complete"] is True
    assert summary["result"]["file_count"] == 2

    indexed = handle(
        {
            "id": "search-indexed",
            "action": "search",
            "path": str(nested_app_library),
            "query": "roadway corridor",
            "top_k": 1,
        }
    )
    assert indexed["ok"] is True
    assert indexed["result"][0]["file"].endswith("roadway.vera")

    water_path = nested_app_library / "utilities" / "water.vera"
    narrowed = handle(
        {
            "id": "search-narrowed",
            "action": "search",
            "path": str(nested_app_library),
            "paths": [str(water_path)],
            "query": "roadway corridor",
            "top_k": 1,
        }
    )
    assert narrowed["ok"] is True
    assert narrowed["result"][0]["file"] == str(water_path)

    bridge = nested_app_library / "transportation" / "bridges" / "bridge.vera"
    bridge.parent.mkdir(parents=True)
    bridge_pdf = bridge.with_suffix(".pdf")
    make_topic_pdf(
        bridge_pdf,
        "Bridge Inspection",
        "Our team completed bridge inspection and rehabilitation design.",
    )
    convert(str(bridge_pdf), str(bridge), model="hashing")

    stale = handle(
        {
            "id": "status-stale",
            "action": "index_status",
            "path": str(nested_app_library),
            "verify_hashes": False,
        }
    )
    assert stale["ok"] is True
    assert stale["result"]["exists"] is True
    assert stale["result"]["fresh"] is False

    updated = handle(
        {
            "id": "index-update",
            "action": "index_update",
            "path": str(nested_app_library),
        }
    )
    assert updated["ok"] is True
    assert updated["result"]["operation"] == "update"
    assert updated["result"]["indexed"] == 3


def test_index_build_streams_request_scoped_progress(monkeypatch, nested_app_library):
    sidecar = importlib.import_module("vera_app.sidecar")
    emitted = []
    monkeypatch.setattr(sidecar, "_write_response", emitted.append)

    response = sidecar.handle(
        {
            "id": "index-progress",
            "action": "index_build",
            "path": str(nested_app_library),
            "recursive": True,
        }
    )

    assert response["ok"] is True
    progress = [event for event in emitted if event.get("event") == "index_progress"]
    assert progress
    assert {event["id"] for event in progress} == {"index-progress"}
    assert progress[0]["phase"] == "discovering"
    assert progress[-1]["phase"] == "finalizing"
    assert progress[-1]["completed"] == progress[-1]["total"] == 2
    assert progress[-1]["chunks"] == response["result"]["chunks"]


def test_search_defers_figure_bytes_until_requested(tmp_path):
    pdf = tmp_path / "manual.pdf"
    out = tmp_path / "manual.vera"
    make_structured_pdf(pdf)
    convert(str(pdf), str(out), model="hashing", store_original=True)

    searched = handle(
        {
            "id": "search",
            "action": "search",
            "path": str(out),
            "query": "restaurant parking",
            "mode": "keyword",
            "top_k": 1,
            "include_figures": True,
            "include_figure_data": False,
        }
    )

    assert searched["ok"] is True
    figures = searched["result"][0]["figures"]
    assert figures
    assert "data_url" not in figures[0]

    loaded = handle(
        {
            "id": "figure-data",
            "action": "figure_data",
            "path": str(out),
            "asset_ids": [figures[0]["asset_id"]],
        }
    )

    assert loaded["ok"] is True
    assert [figure["asset_id"] for figure in loaded["result"]] == [figures[0]["asset_id"]]
    assert loaded["result"][0]["data_url"].startswith("data:image/")


def test_library_inspect_streams_request_scoped_progress(monkeypatch, nested_app_library):
    sidecar = importlib.import_module("vera_app.sidecar")
    emitted = []
    monkeypatch.setattr(sidecar, "_write_response", emitted.append)

    response = sidecar.handle(
        {
            "id": "inspection-progress",
            "action": "inspect",
            "path": str(nested_app_library),
            "recursive": True,
        }
    )

    assert response["ok"] is True
    progress = [event for event in emitted if event.get("event") == "inspection_progress"]
    assert progress
    assert {event["id"] for event in progress} == {"inspection-progress"}
    assert progress[-1]["completed"] == progress[-1]["total"] == 2
    assert progress[-1]["chunks"] == response["result"]["chunks"]


@pytest.mark.parametrize(
    ("action", "expected_error"),
    [
        ("inspect", "Inspection cancelled"),
        ("source", "Source loading cancelled"),
        ("search", "Search cancelled"),
    ],
)
def test_inspection_and_source_honor_cancellation(action, expected_error):
    cancel = CancellationToken()
    cancel.cancel()

    response = handle(
        {
            "id": f"cancel-{action}",
            "action": action,
            "path": "unused",
        },
        cancel=cancel,
    )

    assert response["ok"] is False
    assert response["cancelled"] is True
    assert response["error"] == expected_error


@pytest.mark.parametrize(
    "background_action",
    ["index_build", "inspect", "search", "list_models", "figure_data", "export"],
)
def test_library_work_does_not_block_other_sidecar_requests(monkeypatch, background_action):
    sidecar = importlib.import_module("vera_app.sidecar")
    work_started = threading.Event()
    release_work = threading.Event()
    work_finished = threading.Event()
    all_responses = threading.Event()
    responses = []
    observed = {"ping_while_working": False}

    def fake_handle(request, cancel=None):
        if request["action"] == background_action:
            work_started.set()
            release_work.wait(timeout=1)
            work_finished.set()
        elif request["action"] == "ping":
            observed["ping_while_working"] = work_started.is_set() and not work_finished.is_set()
            release_work.set()
        return {"id": request["id"], "ok": True, "result": request["action"]}

    def capture_response(response):
        responses.append(response)
        if len(responses) == 2:
            all_responses.set()

    monkeypatch.setattr(sidecar, "handle", fake_handle)
    monkeypatch.setattr(sidecar, "_write_response", capture_response)
    monkeypatch.setattr(
        sidecar.sys,
        "stdin",
        io.StringIO(
            f'{{"id":"work","action":"{background_action}","path":"library"}}\n'
            '{"id":"ping","action":"ping"}\n'
        ),
    )

    assert sidecar.main() == 0
    assert all_responses.wait(timeout=1)
    assert observed["ping_while_working"] is True
    assert {response["id"] for response in responses} == {"work", "ping"}


def test_search_action_can_be_cancelled_while_in_flight(monkeypatch):
    sidecar = importlib.import_module("vera_app.sidecar")
    search_started = threading.Event()
    control_acked = threading.Event()
    release_search = threading.Event()
    all_responses = threading.Event()
    responses = []
    stdin = _ScriptedStdin()

    def fake_search(request, cancel=None):
        assert cancel is not None
        search_started.set()
        assert release_search.wait(timeout=2)
        cancel.raise_if_cancelled()
        return []

    def capture_response(response):
        responses.append(response)
        if response.get("id") == "cancel":
            control_acked.set()
        if len(responses) >= 3:
            all_responses.set()

    monkeypatch.setattr(sidecar, "_search", fake_search)
    monkeypatch.setattr(sidecar, "_write_response", capture_response)
    monkeypatch.setattr(sidecar.sys, "stdin", stdin)

    thread = threading.Thread(target=sidecar.main, daemon=True)
    thread.start()
    stdin.push('{"id":"search","action":"search","path":"manual.vera","query":"detention"}\n')
    assert search_started.wait(timeout=2)
    stdin.push('{"id":"ping","action":"ping"}\n')
    stdin.push('{"id":"cancel","action":"cancel","target_id":"search"}\n')
    assert control_acked.wait(timeout=2)
    release_search.set()
    stdin.push(None)
    thread.join(timeout=2)
    assert all_responses.wait(timeout=2)

    ping_response = next(item for item in responses if item.get("id") == "ping")
    cancel_response = next(item for item in responses if item.get("id") == "cancel")
    search_response = next(item for item in responses if item.get("id") == "search")
    assert ping_response["ok"] is True
    assert cancel_response["ok"] is True
    assert cancel_response["result"]["cancelled"] is True
    assert search_response == {
        "id": "search",
        "ok": False,
        "error": "Search cancelled",
        "cancelled": True,
    }


@pytest.mark.parametrize(
    ("action", "request_line"),
    [
        (
            "convert",
            '{"id":"convert","action":"convert","input":"manual.pdf","output":"manual.vera"}',
        ),
        ("batch_convert", '{"id":"batch","action":"batch_convert","directory":"library"}'),
    ],
)
def test_conversion_actions_do_not_block_other_sidecar_requests(monkeypatch, action, request_line):
    sidecar = importlib.import_module("vera_app.sidecar")
    conversion_started = threading.Event()
    release_conversion = threading.Event()
    conversion_finished = threading.Event()
    all_responses = threading.Event()
    responses = []
    observed = {"ping_while_converting": False}

    def fake_handle(incoming_request, cancel=None):
        if incoming_request["action"] == action:
            conversion_started.set()
            release_conversion.wait(timeout=1)
            conversion_finished.set()
        elif incoming_request["action"] == "ping":
            observed["ping_while_converting"] = (
                conversion_started.is_set() and not conversion_finished.is_set()
            )
            release_conversion.set()
        return {"id": incoming_request["id"], "ok": True, "result": incoming_request["action"]}

    def capture_response(response):
        responses.append(response)
        if len(responses) == 2:
            all_responses.set()

    monkeypatch.setattr(sidecar, "handle", fake_handle)
    monkeypatch.setattr(sidecar, "_write_response", capture_response)
    monkeypatch.setattr(
        sidecar.sys,
        "stdin",
        io.StringIO(f'{request_line}\n{{"id":"ping","action":"ping"}}\n'),
    )

    assert sidecar.main() == 0
    assert all_responses.wait(timeout=1)
    assert observed["ping_while_converting"] is True
    assert {response["id"] for response in responses} == {
        "convert" if action == "convert" else "batch",
        "ping",
    }


def test_empty_library_can_open_for_summary(tmp_path):
    response = handle(
        {
            "id": "inspect-empty-library",
            "action": "inspect",
            "path": str(tmp_path),
            "summary_only": True,
            "default_recursive": True,
            "allow_empty": True,
        }
    )

    assert response["ok"] is True
    assert response["result"]["directory"] == str(tmp_path.resolve())
    assert response["result"]["file_count"] == 0
    assert response["result"]["discovered_file_count"] == 0
    assert response["result"]["summary_source"] == "discovery"


def test_single_file_scope_still_stamps_source_path(tmp_path):
    pdf = tmp_path / "manual.pdf"
    out = tmp_path / "manual.vera"
    make_pdf(pdf)
    convert(str(pdf), str(out), model="hashing")

    response = handle(
        {
            "id": "single-search",
            "action": "search",
            "path": str(out),
            "paths": [str(out)],
            "query": "restaurant parking",
            "top_k": 1,
        }
    )

    assert response["ok"] is True
    assert response["result"][0]["file"] == str(out)


def test_batch_convert_supports_recursive_discovery_and_default_names(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    top_pdf = root / "top-level.pdf"
    nested_pdf = root / "transportation" / "nested-proposal.PDF"
    nested_pdf.parent.mkdir()
    make_pdf(top_pdf)
    make_pdf(nested_pdf)

    top_only = handle(
        {
            "id": "batch-top",
            "action": "batch_convert",
            "directory": str(root),
            "recursive": False,
            "model": "hashing",
        }
    )

    assert top_only["ok"] is True
    assert top_only["result"]["discovered"] == 1
    assert top_only["result"]["converted"] == 1
    assert (root / "top-level.vera").is_file()
    assert not (nested_pdf.parent / "nested-proposal.vera").exists()

    recursive = handle(
        {
            "id": "batch-recursive",
            "action": "batch_convert",
            "directory": str(root),
            "recursive": True,
            "model": "hashing",
        }
    )

    assert recursive["ok"] is True
    assert recursive["result"]["discovered"] == 2
    assert recursive["result"]["converted"] == 1
    assert recursive["result"]["skipped"] == 1
    assert recursive["result"]["malformed"] == 0
    assert recursive["result"]["malformed_existing"] == []
    assert recursive["result"]["failed"] == 0
    assert (nested_pdf.parent / "nested-proposal.vera").is_file()


def test_batch_convert_paths_converts_only_selected_pdfs(tmp_path):
    root = tmp_path / "library"
    root.mkdir()
    first = root / "first.pdf"
    second = root / "second.pdf"
    ignored = root / "ignored.pdf"
    make_pdf(first)
    make_pdf(second)
    make_pdf(ignored)

    response = handle(
        {
            "id": "batch-paths",
            "action": "batch_convert",
            "paths": [str(first), str(second)],
            "model": "hashing",
        }
    )

    assert response["ok"] is True
    assert response["result"]["discovered"] == 2
    assert response["result"]["converted"] == 2
    assert response["result"]["recursive"] is False
    assert (root / "first.vera").is_file()
    assert (root / "second.vera").is_file()
    assert not (root / "ignored.vera").exists()


def test_sidecar_forwards_ocr_options_for_single_and_batch_conversion(monkeypatch):
    sidecar = importlib.import_module("vera_app.sidecar")
    captured = {}

    def fake_convert(input_path, output_path, **kwargs):
        captured["single"] = (input_path, output_path, kwargs)
        return output_path

    def fake_batch_convert(directory, **kwargs):
        captured["batch"] = (directory, kwargs)
        return {"converted": 0, "failed": 0}

    monkeypatch.setattr(sidecar, "convert", fake_convert)
    monkeypatch.setattr(sidecar, "batch_convert", fake_batch_convert)

    single = handle(
        {
            "id": "ocr-single",
            "action": "convert",
            "input": "scan.pdf",
            "output": "scan.vera",
            "ocr_mode": "force",
            "ocr_language": "spa",
            "ocr_dpi": 240,
        }
    )
    batch = handle(
        {
            "id": "ocr-batch",
            "action": "batch_convert",
            "directory": "scans",
            "ocr_mode": "off",
            "ocr_language": "deu",
            "ocr_dpi": 200,
        }
    )

    assert single["ok"] is True
    assert captured["single"][2]["ocr_mode"] == "force"
    assert captured["single"][2]["ocr_language"] == "spa"
    assert captured["single"][2]["ocr_dpi"] == 240
    assert captured["single"][2]["model"] == "hashing"
    assert batch["ok"] is True
    assert captured["batch"][1]["ocr_mode"] == "off"
    assert captured["batch"][1]["ocr_language"] == "deu"
    assert captured["batch"][1]["ocr_dpi"] == 200
    assert captured["batch"][1]["model"] == "hashing"


def test_sidecar_describe_ingest_pipelines_and_pipeline_options(monkeypatch):
    sidecar = importlib.import_module("vera_app.sidecar")
    captured = {}

    class FakeDescriptor:
        def as_dict(self):
            return {
                "provider": "pymupdf",
                "variant": "",
                "spec": "pymupdf",
                "label": "pymupdf",
                "description": "built-in",
                "installed": True,
                "capabilities": {"overlap_supported": True},
                "fields": [{"key": "chunk_size", "type": "integer", "default": 500}],
                "notes": [],
            }

    def fake_convert(input_path, output_path, **kwargs):
        captured["single"] = kwargs
        return output_path

    def fake_batch_convert(directory, **kwargs):
        captured["batch"] = kwargs
        return {"converted": 0, "failed": 0}

    monkeypatch.setattr(sidecar, "convert", fake_convert)
    monkeypatch.setattr(sidecar, "batch_convert", fake_batch_convert)
    monkeypatch.setattr(
        sidecar,
        "list_ingest_pipeline_descriptors",
        lambda: [FakeDescriptor()],
    )

    described = handle({"id": "desc", "action": "describe_ingest_pipelines"})
    single = handle(
        {
            "id": "opts-single",
            "action": "convert",
            "input": "scan.pdf",
            "output": "scan.vera",
            "parser": "pymupdf",
            "pipeline_options": {"chunk_size": 800, "ocr_mode": "force"},
        }
    )
    batch = handle(
        {
            "id": "opts-batch",
            "action": "batch_convert",
            "directory": "scans",
            "parser": "docling",
            "pipeline_options": {"chunk_size": 250, "ocr_language": "en"},
        }
    )

    assert described["ok"] is True
    assert described["result"]["pipelines"][0]["spec"] == "pymupdf"
    assert described["result"]["pipelines"][0]["fields"][0]["key"] == "chunk_size"
    assert single["ok"] is True
    assert captured["single"]["pipeline_options"] == {"chunk_size": 800, "ocr_mode": "force"}
    assert "chunk_size" not in captured["single"]
    assert "ocr_mode" not in captured["single"]
    assert "ocr_language" not in captured["single"]
    assert batch["ok"] is True
    assert captured["batch"]["pipeline_options"] == {"chunk_size": 250, "ocr_language": "en"}
    assert captured["batch"]["parser"] == "docling"
    assert "chunk_size" not in captured["batch"]
    assert "ocr_language" not in captured["batch"]


def test_sidecar_default_ocr_language_is_not_forwarded_to_docling(monkeypatch):
    pytest.importorskip("vera_ingest_docling")
    from vera_ingest import prepare_pipeline_options
    from vera_ingest_docling.options import DoclingOptions

    sidecar = importlib.import_module("vera_app.sidecar")
    captured = {}

    def fake_convert(input_path, output_path, **kwargs):
        captured.update(kwargs)
        return output_path

    monkeypatch.setattr(sidecar, "convert", fake_convert)
    response = handle(
        {
            "id": "docling-ocr-default",
            "action": "convert",
            "input": "scan.pdf",
            "output": "scan.vera",
            "parser": "docling",
        }
    )

    assert response["ok"] is True
    assert "ocr_language" not in captured
    assert "chunk_size" not in captured
    assert "ocr_mode" not in captured
    merged = prepare_pipeline_options(
        spec=captured["parser"],
        pipeline_options=captured.get("pipeline_options"),
        legacy_options={
            key: captured[key]
            for key in (
                "chunk_size",
                "overlap",
                "ocr_mode",
                "ocr_language",
                "ocr_dpi",
                "ocr_download",
            )
            if key in captured
        },
    )
    assert "ocr_language" not in merged
    assert DoclingOptions.from_mapping(merged).ocr_language == "en"


def test_sidecar_forwards_ocr_download_flag(monkeypatch):
    sidecar = importlib.import_module("vera_app.sidecar")
    captured = {}

    def fake_convert(input_path, output_path, **kwargs):
        captured["single"] = kwargs
        return output_path

    monkeypatch.setattr(sidecar, "convert", fake_convert)

    response = handle(
        {
            "id": "ocr-download-flag",
            "action": "convert",
            "input": "scan.pdf",
            "output": "scan.vera",
            "ocr_language": "fra",
            "ocr_download": True,
        }
    )

    assert response["ok"] is True
    assert captured["single"]["ocr_download"] is True


def test_sidecar_ocr_languages_list_reports_bundled_and_unknown():
    response = handle({"id": "ocr-list", "action": "ocr_languages_list", "language": "eng+zzz"})

    assert response["ok"] is True
    codes = {entry["code"]: entry for entry in response["result"]["languages"]}
    assert codes["eng"]["bundled"] is True
    assert codes["zzz"]["downloadable"] is False


def test_sidecar_ocr_languages_download_streams_progress_and_returns_cache_dir(monkeypatch):
    sidecar = importlib.import_module("vera_app.sidecar")
    emitted = []
    monkeypatch.setattr(sidecar, "_write_response", emitted.append)

    def fake_download(language, *, progress=None, **kwargs):
        if progress:
            progress(language, 50, 100)
            progress(language, 100, 100)
        return "/fake/cache/dir"

    monkeypatch.setattr(sidecar, "download_ocr_language_data", fake_download)

    response = sidecar.handle(
        {"id": "ocr-download", "action": "ocr_languages_download", "language": "fra"}
    )

    assert response["ok"] is True
    assert response["result"] == {
        "language": "fra",
        "downloaded": ["fra"],
        "cache_dir": "/fake/cache/dir",
    }
    progress_events = [event for event in emitted if event.get("event") == "ocr_download_progress"]
    assert [event["downloaded"] for event in progress_events] == [50, 100]
    assert all(event["id"] == "ocr-download" for event in progress_events)


def test_sidecar_ocr_languages_download_unknown_language_fails(monkeypatch):
    response = handle({"id": "ocr-bad", "action": "ocr_languages_download", "language": "zzz"})

    assert response["ok"] is False
    assert "zzz" in response["error"]


def test_sidecar_ocr_languages_download_requires_language():
    response = handle({"id": "ocr-empty", "action": "ocr_languages_download", "language": ""})

    assert response["ok"] is False
    assert "language is required" in response["error"]


def test_sidecar_forwards_embedding_model_and_lists_providers(monkeypatch):
    sidecar = importlib.import_module("vera_app.sidecar")
    captured = {}

    def fake_convert(input_path, output_path, **kwargs):
        captured["model"] = kwargs["model"]
        return output_path

    monkeypatch.setattr(sidecar, "convert", fake_convert)
    monkeypatch.setattr(
        sidecar,
        "list_embedding_providers",
        lambda: ["hashing", "openai"],
    )

    converted = handle(
        {
            "id": "openai-convert",
            "action": "convert",
            "input": "manual.pdf",
            "output": "manual.vera",
            "model": "openai:text-embedding-3-small",
        }
    )
    providers = handle({"id": "embedding-providers", "action": "list_embedding_providers"})
    described = handle(
        {"id": "embedding-providers-describe", "action": "describe_embedding_providers"}
    )
    models = handle(
        {
            "id": "embedding-models",
            "action": "list_embedding_models",
            "provider": "hashing",
        }
    )
    preflight = handle(
        {"id": "embedding-preflight", "action": "preflight_embedder", "model": "hashing"}
    )

    assert converted["ok"] is True
    assert captured["model"] == "openai:text-embedding-3-small"
    assert providers == {
        "id": "embedding-providers",
        "ok": True,
        "result": {"providers": ["hashing", "openai"]},
    }
    assert described["ok"] is True
    assert "providers" in described["result"]
    assert isinstance(described["result"]["providers"], list)
    assert models["ok"] is True
    assert models["result"]["provider"] == "hashing"
    assert models["result"]["models"][0]["model_id"] == "vera-hashing-384"
    assert preflight["ok"] is True
    assert preflight["result"]["ok"] is True
    assert preflight["result"]["provider"] == "hashing"


def test_source_action_materializes_cache_file(tmp_path):
    pdf = tmp_path / "manual.pdf"
    out = tmp_path / "manual.vera"
    cache_dir = tmp_path / "source-cache"
    make_pdf(pdf)
    convert(str(pdf), str(out), model="hashing", store_original=True)

    response = handle(
        {
            "id": "1",
            "action": "source",
            "path": str(out),
            "cache_dir": str(cache_dir),
        }
    )

    assert response["ok"] is True
    result = response["result"]
    assert result["filename"] == "manual.pdf"
    assert result["mime_type"] == "application/pdf"
    assert result["size"] > 0
    assert result["hash"]
    assert "data_url" not in result
    cache_path = Path(result["cache_path"])
    assert cache_path.is_file()
    assert cache_path.resolve().parent == cache_dir.resolve()
    assert cache_path.stat().st_size == result["size"]
    assert cache_path.read_bytes().startswith(b"%PDF")

    # Second load reuses the same hash-keyed cache file.
    again = handle(
        {
            "id": "2",
            "action": "source",
            "path": str(out),
            "cache_dir": str(cache_dir),
        }
    )
    assert again["ok"] is True
    assert again["result"]["cache_path"] == result["cache_path"]


def test_source_action_loads_filesystem_pdf(tmp_path):
    pdf = tmp_path / "manual.pdf"
    cache_dir = tmp_path / "source-cache"
    make_pdf(pdf)

    response = handle(
        {
            "id": "1",
            "action": "source",
            "path": str(pdf),
            "cache_dir": str(cache_dir),
        }
    )

    assert response["ok"] is True
    result = response["result"]
    assert result["filename"] == "manual.pdf"
    assert result["mime_type"] == "application/pdf"
    assert result["size"] == pdf.stat().st_size
    assert result["hash"]
    cache_path = Path(result["cache_path"])
    assert cache_path.is_file()
    assert cache_path.resolve().parent == cache_dir.resolve()
    assert cache_path.read_bytes() == pdf.read_bytes()

    again = handle(
        {
            "id": "2",
            "action": "source",
            "path": str(pdf),
            "cache_dir": str(cache_dir),
        }
    )
    assert again["ok"] is True
    assert again["result"]["cache_path"] == result["cache_path"]


def test_source_action_reuses_cache_without_extracting_blob(tmp_path, monkeypatch):
    pdf = tmp_path / "manual.pdf"
    out = tmp_path / "manual.vera"
    cache_dir = tmp_path / "source-cache"
    make_pdf(pdf)
    convert(str(pdf), str(out), model="hashing", store_original=True)
    first = handle(
        {
            "id": "1",
            "action": "source",
            "path": str(out),
            "cache_dir": str(cache_dir),
        }
    )
    assert first["ok"] is True

    sidecar = importlib.import_module("vera_app.sidecar")

    def fail_extract(*args, **kwargs):
        raise AssertionError("cache hit should not extract the embedded PDF")

    monkeypatch.setattr(sidecar.VeraDocument, "write_attachment", fail_extract)
    again = handle(
        {
            "id": "2",
            "action": "source",
            "path": str(out),
            "cache_dir": str(cache_dir),
        }
    )
    assert again["ok"] is True
    assert again["result"]["cache_path"] == first["result"]["cache_path"]


def test_source_action_copies_sibling_pdf_instead_of_embedded_blob(tmp_path, monkeypatch):
    pdf = tmp_path / "manual.pdf"
    out = tmp_path / "manual.vera"
    cache_dir = tmp_path / "source-cache"
    make_pdf(pdf)
    convert(str(pdf), str(out), model="hashing", store_original=True)
    sidecar = importlib.import_module("vera_app.sidecar")

    def fail_extract(*args, **kwargs):
        raise AssertionError("matching sibling PDF should be copied instead of extracted")

    monkeypatch.setattr(sidecar.VeraDocument, "write_attachment", fail_extract)
    response = handle(
        {
            "id": "1",
            "action": "source",
            "path": str(out),
            "cache_dir": str(cache_dir),
        }
    )
    assert response["ok"] is True
    cache_path = Path(response["result"]["cache_path"])
    assert cache_path.read_bytes() == pdf.read_bytes()


def test_source_action_uses_sibling_when_original_is_not_stored(tmp_path):
    pdf = tmp_path / "manual.pdf"
    out = tmp_path / "manual.vera"
    cache_dir = tmp_path / "source-cache"
    make_pdf(pdf)
    convert(str(pdf), str(out), model="hashing", store_original=False)

    response = handle(
        {
            "id": "1",
            "action": "source",
            "path": str(out),
            "cache_dir": str(cache_dir),
        }
    )
    assert response["ok"] is True
    assert Path(response["result"]["cache_path"]).read_bytes() == pdf.read_bytes()


def test_source_action_extracts_embedded_pdf_when_sibling_is_missing(tmp_path):
    pdf = tmp_path / "manual.pdf"
    out = tmp_path / "manual.vera"
    cache_dir = tmp_path / "source-cache"
    make_pdf(pdf)
    convert(str(pdf), str(out), model="hashing", store_original=True)
    expected = pdf.read_bytes()
    pdf.unlink()

    response = handle(
        {
            "id": "1",
            "action": "source",
            "path": str(out),
            "cache_dir": str(cache_dir),
        }
    )
    assert response["ok"] is True
    assert Path(response["result"]["cache_path"]).read_bytes() == expected


def test_answer_action_requires_llm(tmp_path):
    pdf = tmp_path / "manual.pdf"
    out = tmp_path / "manual.vera"
    make_pdf(pdf)
    convert(str(pdf), str(out), model="hashing", store_original=True)

    response = handle(
        {"id": "1", "action": "answer", "path": str(out), "prompt": "restaurant parking"}
    )

    assert response["ok"] is False
    assert "model must be selected" in response["error"].lower()


def test_provider_http_error_includes_raw_detail_for_debugging(monkeypatch):
    sidecar = importlib.import_module("vera_app.sidecar")
    raw_detail = '{"error":{"message":"context window exceeded","code":"context_length_exceeded"}}'

    def fail_answer(*args, **kwargs):
        raise ProviderHttpError(400, raw_detail)

    monkeypatch.setattr(sidecar, "_answer", fail_answer)

    response = sidecar.handle({"id": "provider-error", "action": "answer"})

    assert response["ok"] is False
    assert response["error"] == "LLM provider request failed (HTTP 400): context window exceeded"
    assert response["provider_error_detail"] == raw_detail


def test_answer_action_returns_structured_cancellation(tmp_path, monkeypatch):
    pdf = tmp_path / "manual.pdf"
    out = tmp_path / "manual.vera"
    make_pdf(pdf)
    convert(str(pdf), str(out), model="hashing", store_original=True)
    cancel = CancellationToken()

    def fake_chat(messages, config, tools=None, tool_choice="auto", on_delta=None, cancel=None):
        assert cancel is not None
        cancel.cancel()
        return ChatResponse(
            content="Partial answer",
            tool_calls=[],
            message={"role": "assistant", "content": "Partial answer"},
            model="test-model",
        )

    monkeypatch.setattr("vera_app.sidecar.chat", fake_chat)

    response = handle(
        {
            "id": "cancelled",
            "action": "answer",
            "path": str(out),
            "prompt": "restaurant parking",
            "llm": _llm_payload(),
        },
        cancel=cancel,
    )

    assert response == {
        "id": "cancelled",
        "ok": False,
        "error": "Answer cancelled",
        "cancelled": True,
    }


def test_conversion_actions_can_be_cancelled(monkeypatch):
    sidecar = importlib.import_module("vera_app.sidecar")
    conversion_started = threading.Event()
    control_acked = threading.Event()
    release_conversion = threading.Event()
    all_responses = threading.Event()
    responses = []
    stdin = _ScriptedStdin()

    def fake_batch_convert(directory, **kwargs):
        cancel = kwargs.get("cancel")
        assert cancel is not None
        conversion_started.set()
        assert release_conversion.wait(timeout=2)
        cancel.raise_if_cancelled()
        return {"converted": 1}

    def capture_response(response):
        # Progress events share the request id but are not final responses.
        if "event" in response and "ok" not in response:
            return
        responses.append(response)
        if response.get("id") in {"cancel", "skip"}:
            control_acked.set()
        if len(responses) >= 2:
            all_responses.set()

    monkeypatch.setattr(sidecar, "batch_convert", fake_batch_convert)
    monkeypatch.setattr(sidecar, "_write_response", capture_response)
    monkeypatch.setattr(sidecar.sys, "stdin", stdin)

    thread = threading.Thread(target=sidecar.main, daemon=True)
    thread.start()
    stdin.push('{"id":"batch","action":"batch_convert","directory":"library"}\n')
    assert conversion_started.wait(timeout=2)
    stdin.push('{"id":"cancel","action":"cancel","target_id":"batch"}\n')
    assert control_acked.wait(timeout=2)
    release_conversion.set()
    stdin.push(None)
    thread.join(timeout=2)
    assert all_responses.wait(timeout=2)

    cancel_response = next(item for item in responses if item.get("id") == "cancel")
    batch_response = next(item for item in responses if item.get("id") == "batch")
    assert cancel_response["ok"] is True
    assert cancel_response["result"]["cancelled"] is True
    assert batch_response == {
        "id": "batch",
        "ok": False,
        "error": "Conversion cancelled",
        "cancelled": True,
    }


def test_convert_action_returns_structured_cancellation(monkeypatch):
    sidecar = importlib.import_module("vera_app.sidecar")
    cancel = CancellationToken()
    cancel.cancel()

    def fake_convert(*args, **kwargs):
        assert kwargs.get("cancel") is cancel
        cancel.raise_if_cancelled()

    monkeypatch.setattr(sidecar, "convert", fake_convert)

    response = sidecar.handle(
        {
            "id": "convert-cancelled",
            "action": "convert",
            "input": "manual.pdf",
            "output": "manual.vera",
        },
        cancel=cancel,
    )

    assert response == {
        "id": "convert-cancelled",
        "ok": False,
        "error": "Conversion cancelled",
        "cancelled": True,
    }


def test_batch_convert_skip_request_continues_remaining_files(monkeypatch):
    sidecar = importlib.import_module("vera_app.sidecar")
    conversion_started = threading.Event()
    control_acked = threading.Event()
    release_conversion = threading.Event()
    all_responses = threading.Event()
    responses = []
    seen_skip = {"value": False}
    stdin = _ScriptedStdin()

    def fake_batch_convert(directory, **kwargs):
        cancel = kwargs.get("cancel")
        assert cancel is not None
        conversion_started.set()
        assert release_conversion.wait(timeout=2)
        try:
            cancel.raise_if_interrupted()
        except Exception:
            seen_skip["value"] = cancel.skip_requested
            cancel.clear_skip()
            return {
                "converted": 1,
                "user_skipped": 1,
                "skipped_by_user": ["slow.pdf"],
                "failed": 0,
            }
        return {"converted": 2, "user_skipped": 0, "skipped_by_user": [], "failed": 0}

    def capture_response(response):
        if "event" in response and "ok" not in response:
            return
        responses.append(response)
        if response.get("id") in {"cancel", "skip"}:
            control_acked.set()
        if len(responses) >= 2:
            all_responses.set()

    monkeypatch.setattr(sidecar, "batch_convert", fake_batch_convert)
    monkeypatch.setattr(sidecar, "_write_response", capture_response)
    monkeypatch.setattr(sidecar.sys, "stdin", stdin)

    thread = threading.Thread(target=sidecar.main, daemon=True)
    thread.start()
    stdin.push('{"id":"batch","action":"batch_convert","directory":"library"}\n')
    assert conversion_started.wait(timeout=2)
    stdin.push('{"id":"skip","action":"skip","target_id":"batch"}\n')
    assert control_acked.wait(timeout=2)
    release_conversion.set()
    stdin.push(None)
    thread.join(timeout=2)
    assert all_responses.wait(timeout=2)

    skip_response = next(item for item in responses if item.get("id") == "skip")
    batch_response = next(item for item in responses if item.get("id") == "batch")
    assert skip_response["ok"] is True
    assert skip_response["result"]["skipped"] is True
    assert seen_skip["value"] is True
    assert batch_response["ok"] is True
    assert batch_response["result"]["user_skipped"] == 1


def test_answer_action_runs_agentic_search(tmp_path, monkeypatch):
    pdf = tmp_path / "manual.pdf"
    out = tmp_path / "manual.vera"
    make_pdf(pdf)
    convert(str(pdf), str(out), model="hashing", store_original=True)

    calls = {"n": 0}
    emitted: list[dict] = []

    def fake_chat(messages, config, tools=None, tool_choice="auto", on_delta=None):
        calls["n"] += 1
        assert on_delta is not None
        if calls["n"] == 1:
            assert tools, "tools should be offered on the first turn"
            assert config.model == "test-model"
            on_delta("Checking the library. ")
            on_delta("<tool_")
            on_delta('call>{"query":"restaurant parking"}</tool_call>')
            return ChatResponse(
                content='<tool_call>{"query":"restaurant parking"}</tool_call>',
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        name="search",
                        arguments={"query": "restaurant parking", "mode": "keyword", "top_k": 1},
                    )
                ],
                message={
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "search", "arguments": "{}"},
                        }
                    ],
                },
                model="test-model",
                usage=None,
            )
        joined = json.dumps(messages)
        assert "C1" in joined, "tool result with citation should be fed back to the model"
        assert "parking" in joined.lower()
        on_delta("Restaurant parking requirements ")
        on_delta("are in the cited passage. [C1]")
        return ChatResponse(
            content="Restaurant parking requirements are in the cited passage. [C1]",
            tool_calls=[],
            message={"role": "assistant", "content": "done"},
            model="test-model",
            usage={"total_tokens": 42},
        )

    monkeypatch.setattr("vera_app.sidecar.chat", fake_chat)
    monkeypatch.setattr("vera_app.sidecar._write_response", emitted.append)

    response = handle(
        {
            "id": "1",
            "action": "answer",
            "path": str(out),
            "prompt": "restaurant parking",
            "llm": _llm_payload(),
        }
    )

    assert response["ok"] is True
    result = response["result"]
    assert result["answer_mode"] == "agent"
    assert result["answer"].endswith("[C1]")
    assert result["citations"][0]["id"] == "C1"
    assert result["citations"][0]["result"]["regions"]
    assert result["searches"][0]["query"] == "restaurant parking"
    assert result["llm"]["model"] == "test-model"
    trace_events = [event["event"] for event in result["trace"]]
    assert trace_events.count("search_start") == 1
    assert trace_events.count("search_done") == 1
    assert "answer_delta" not in trace_events
    assert "answer_reset" not in trace_events
    answer_events = [
        (event.get("event"), event.get("text"))
        for event in emitted
        if event.get("event") in {"answer_delta", "answer_reset"}
    ]
    assert answer_events == [
        ("answer_delta", "Checking the library. "),
        ("answer_reset", None),
        ("answer_delta", "Restaurant parking requirements "),
        ("answer_delta", "are in the cited passage. [C1]"),
    ]
    assert all("<tool_call>" not in str(event.get("text", "")) for event in emitted)


def test_answer_action_merges_custom_instructions(tmp_path, monkeypatch):
    pdf = tmp_path / "manual.pdf"
    out = tmp_path / "manual.vera"
    make_pdf(pdf)
    convert(str(pdf), str(out), model="hashing", store_original=True)

    seen = {}

    def fake_chat(messages, config, tools=None, tool_choice="auto", on_delta=None):
        seen["system"] = messages[0]["content"]
        return ChatResponse(
            content="Answer.",
            tool_calls=[],
            message={"role": "assistant", "content": "Answer."},
            model="test-model",
            usage=None,
        )

    monkeypatch.setattr("vera_app.sidecar.chat", fake_chat)

    response = handle(
        {
            "id": "1",
            "action": "answer",
            "path": str(out),
            "prompt": "restaurant parking",
            "instructions": "Respond as a compliance checklist.",
            "llm": _llm_payload(),
        }
    )

    assert response["ok"] is True
    result = response["result"]
    assert "Additional response instructions" in result["instructions"]
    assert "Respond as a compliance checklist" in result["instructions"]
    assert "Additional response instructions" in seen["system"]


def test_answer_action_falls_back_when_tools_unsupported(tmp_path, monkeypatch):
    pdf = tmp_path / "manual.pdf"
    out = tmp_path / "manual.vera"
    make_pdf(pdf)
    convert(str(pdf), str(out), model="hashing", store_original=True)

    def fake_chat(messages, config, tools=None, tool_choice="auto", on_delta=None):
        raise ToolsUnsupportedError("this model does not support tools")

    emitted: list[dict] = []

    def fake_generate(messages, config, on_delta=None, cancel=None):
        assert "restaurant parking" in messages[-1]["content"]
        assert "[C1]" in messages[-1]["content"]
        assert on_delta is not None
        on_delta("Parking is covered ")
        on_delta("in the cited passage. [C1]")

        class Result:
            answer = "Parking is covered in the cited passage. [C1]"
            provider = "openai_compatible"
            model = "test-model"
            usage = {"total_tokens": 7}

        return Result()

    monkeypatch.setattr("vera_app.sidecar.chat", fake_chat)
    monkeypatch.setattr("vera_app.sidecar.generate", fake_generate)
    monkeypatch.setattr("vera_app.sidecar._write_response", emitted.append)

    response = handle(
        {
            "id": "1",
            "action": "answer",
            "path": str(out),
            "prompt": "restaurant parking",
            "llm": _llm_payload(),
        }
    )

    assert response["ok"] is True
    result = response["result"]
    assert result["answer_mode"] == "retrieval"
    assert result["answer"].endswith("[C1]")
    assert result["citations"][0]["id"] == "C1"
    assert [event["text"] for event in emitted if event.get("event") == "answer_delta"] == [
        "Parking is covered ",
        "in the cited passage. [C1]",
    ]


def _figures_mode_dir(tmp_path, max_figure_images=4):
    """Write a custom mode file with include_figures on, for figure-image tests."""
    modes_dir = tmp_path / "modes"
    modes_dir.mkdir()
    (modes_dir / "figures-test.md").write_text(
        "---\n"
        "name: Figures Test\n"
        "include_figures: true\n"
        f"max_figure_images: {max_figure_images}\n"
        "---\n"
        "Answer using the retrieved evidence.\n",
        encoding="utf-8",
    )
    return str(modes_dir)


def test_answer_action_sends_figure_images_to_llm(tmp_path, monkeypatch):
    pdf = tmp_path / "manual.pdf"
    out = tmp_path / "manual.vera"
    make_structured_pdf(pdf)
    convert(str(pdf), str(out), model="hashing", store_original=True)

    calls = {"n": 0}

    def fake_chat(messages, config, tools=None, tool_choice="auto", on_delta=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return ChatResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        name="search",
                        arguments={"query": "restaurant parking", "mode": "keyword", "top_k": 1},
                    )
                ],
                message={
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "search", "arguments": "{}"},
                        }
                    ],
                },
                model="test-model",
                usage=None,
            )
        # Second turn: the figure image should have been offered as a follow-up
        # multimodal user message after the tool result.
        image_messages = [
            m
            for m in messages
            if isinstance(m.get("content"), list)
            and any(part.get("type") == "image_url" for part in m["content"])
        ]
        assert image_messages, "expected a message carrying an image_url content part"
        image_parts = [
            part for part in image_messages[0]["content"] if part.get("type") == "image_url"
        ]
        assert image_parts[0]["image_url"]["url"].startswith("data:image/")
        return ChatResponse(
            content="Restaurant parking requirements are in the cited passage. [C1]",
            tool_calls=[],
            message={"role": "assistant", "content": "done"},
            model="test-model",
            usage=None,
        )

    monkeypatch.setattr("vera_app.sidecar.chat", fake_chat)

    response = handle(
        {
            "id": "1",
            "action": "answer",
            "path": str(out),
            "prompt": "restaurant parking",
            "modes_dir": _figures_mode_dir(tmp_path),
            "mode_id": "figures-test",
            "llm": _llm_payload(),
        }
    )

    assert response["ok"] is True
    assert calls["n"] == 2
    result = response["result"]
    assert result["answer"].endswith("[C1]")
    # The response reports how many images actually reached the model.
    assert result["images_sent"] == 1
    # Persisted citations retain figure metadata without duplicating image bytes.
    assert result["citations"][0]["result"]["figures"]
    assert "data_url" not in result["citations"][0]["result"]["figures"][0]
    # Trace must redact image bytes rather than embedding the raw data URL.
    request_trace = next(
        e for e in result["trace"] if e["event"] == "llm_request" and e["turn"] == 1
    )
    traced_image_parts = [
        part
        for message in request_trace["messages"]
        if isinstance(message.get("content"), list)
        for part in message["content"]
        if part.get("type") == "image_url"
    ]
    assert traced_image_parts, "expected the traced request to include the image message"
    assert "omitted" in traced_image_parts[0]["image_url"]["url"]


def test_answer_action_falls_back_to_text_when_vision_unsupported(tmp_path, monkeypatch):
    pdf = tmp_path / "manual.pdf"
    out = tmp_path / "manual.vera"
    make_structured_pdf(pdf)
    convert(str(pdf), str(out), model="hashing", store_original=True)

    calls = {"n": 0}

    def fake_chat(messages, config, tools=None, tool_choice="auto", on_delta=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return ChatResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        name="search",
                        arguments={"query": "restaurant parking", "mode": "keyword", "top_k": 1},
                    )
                ],
                message={
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "search", "arguments": "{}"},
                        }
                    ],
                },
                model="test-model",
                usage=None,
            )
        if calls["n"] == 2:
            has_image = any(
                isinstance(m.get("content"), list)
                and any(part.get("type") == "image_url" for part in m["content"])
                for m in messages
            )
            assert has_image, "first retry attempt should still offer the image"
            raise VisionUnsupportedError("model does not accept image content")
        # Third call: the retry after stripping the image message.
        assert not any(
            isinstance(m.get("content"), list)
            and any(part.get("type") == "image_url" for part in m["content"])
            for m in messages
        ), "image content should be stripped after VisionUnsupportedError"
        joined = json.dumps(messages)
        assert "does not support image input" in joined
        return ChatResponse(
            content="Restaurant parking requirements are in the cited passage. [C1]",
            tool_calls=[],
            message={"role": "assistant", "content": "done"},
            model="test-model",
            usage=None,
        )

    monkeypatch.setattr("vera_app.sidecar.chat", fake_chat)

    response = handle(
        {
            "id": "1",
            "action": "answer",
            "path": str(out),
            "prompt": "restaurant parking",
            "modes_dir": _figures_mode_dir(tmp_path),
            "mode_id": "figures-test",
            "llm": _llm_payload(),
        }
    )

    assert response["ok"] is True
    assert calls["n"] == 3
    assert response["result"]["answer"].endswith("[C1]")
    # Images were stripped after the rejection, so none actually reached the model.
    assert response["result"]["images_sent"] == 0
    assert response["result"]["vision_fallback"] is True


def test_list_modes_action_returns_builtin_modes():
    response = handle({"id": "1", "action": "list_modes"})

    assert response["ok"] is True
    ids = {mode["id"] for mode in response["result"]["modes"]}
    assert {"ask", "research", "summarize"} <= ids


def test_llm_config_accepts_injected_api_key():
    config = LlmConfig.from_request(
        {
            "provider": "openai_compatible",
            "model": "gpt-4o-mini",
            "base_url": "https://api.openai.com/v1",
            "auth_type": "api_key",
            "api_key": "secret-key",
        }
    )

    assert config.enabled is True
    assert config.auth_type == "api_key"
    assert config.api_key == "secret-key"


def test_list_models_action_returns_sorted_ids(monkeypatch):
    captured = {}

    def fake_list_models(config):
        captured["base_url"] = config.base_url
        captured["api_key"] = config.api_key
        return ["gpt-4o", "gpt-4o-mini"]

    monkeypatch.setattr("vera_app.sidecar.list_models", fake_list_models)

    response = handle(
        {
            "id": "1",
            "action": "list_models",
            "llm": {
                "provider": "openai_compatible",
                "base_url": "https://api.openai.com/v1",
                "auth_type": "api_key",
                "api_key": "secret-key",
            },
        }
    )

    assert response["ok"] is True
    assert response["result"]["models"] == ["gpt-4o", "gpt-4o-mini"]
    assert captured["base_url"] == "https://api.openai.com/v1"
    assert captured["api_key"] == "secret-key"


def test_list_models_parses_openai_and_ollama_shapes(monkeypatch):
    import vera_app.llm as llm_module

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def read(self):
            return json.dumps(self._payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    payloads = iter(
        [
            {"data": [{"id": "b-model"}, {"id": "a-model"}, {"id": "a-model"}]},
            {"models": [{"name": "llama3.1"}, {"name": "qwen2"}]},
        ]
    )

    def fake_urlopen(request, timeout=None):
        return FakeResponse(next(payloads))

    monkeypatch.setattr(llm_module.urllib.request, "urlopen", fake_urlopen)

    openai_config = LlmConfig.from_request(
        {"base_url": "https://api.openai.com/v1", "auth_type": "none"}
    )
    assert llm_module.list_models(openai_config) == ["a-model", "b-model"]

    ollama_config = LlmConfig.from_request(
        {"base_url": "http://localhost:11434/v1", "auth_type": "none"}
    )
    assert llm_module.list_models(ollama_config) == ["llama3.1", "qwen2"]
