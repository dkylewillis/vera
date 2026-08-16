from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from helpers.pdfs import make_pdf
from vera_ingest.descriptors import PipelineDescriptor
from vera_ingest.pipeline import (
    register_ingest_pipeline,
    register_ingest_pipeline_descriptor,
    reset_ingest_pipeline_registry,
)
from vera_plugin_host.cancellation import CancellationToken
from vera_plugin_host.worker import PROTOCOL_VERSION, handle, handle_convert

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _reset_registry():
    reset_ingest_pipeline_registry()
    yield
    reset_ingest_pipeline_registry()


def test_plugin_host_ping_reports_versions():
    response = handle({"id": "ping", "action": "ping"})
    assert response["ok"] is True
    result = response["result"]
    assert result["protocol"] == PROTOCOL_VERSION
    assert result["protocol"] == 2
    assert result["plugin_api"] == 1
    assert "pymupdf" in result["pipelines"]
    assert "hashing" in result["embedders"]
    assert result["python_executable"]
    assert result["vera_ingest_version"].startswith("0.3.")
    assert result["vera_doc_version"]


def test_plugin_host_describes_registered_plugin():
    register_ingest_pipeline("echo", lambda _variant: lambda *args, **kwargs: args[1], replace=True)
    register_ingest_pipeline_descriptor(
        "echo",
        lambda variant: PipelineDescriptor(
            provider="echo",
            variant=variant,
            spec="echo",
            label="echo",
        ),
        replace=True,
    )
    response = handle({"id": "desc", "action": "describe_ingest_pipelines"})
    assert response["ok"] is True
    specs = {item["spec"] for item in response["result"]["pipelines"]}
    assert "pymupdf" in specs
    assert "echo" in specs


def test_plugin_host_convert_uses_bundled_pymupdf(tmp_path):
    pdf = tmp_path / "manual.pdf"
    output = tmp_path / "manual.vera"
    make_pdf(pdf)
    response = handle(
        {
            "id": "convert",
            "action": "convert",
            "input": str(pdf),
            "output": str(output),
            "parser": "pymupdf",
            "model": "hashing",
        }
    )
    assert response["ok"] is True, response
    assert Path(response["result"]["output"]).is_file()


def test_plugin_host_forwards_pipeline_options(monkeypatch, tmp_path):
    captured: dict = {}

    def fake_convert(source_path, output_path, **options):
        captured.update(options)
        return str(output_path)

    monkeypatch.setattr("vera_plugin_host.worker.convert", fake_convert)
    response = handle(
        {
            "id": "convert",
            "action": "convert",
            "input": str(tmp_path / "manual.pdf"),
            "output": str(tmp_path / "out.vera"),
            "parser": "docling",
            "model": "hashing",
            "pipeline_options": {"chunk_size": 2000, "ocr_mode": "auto"},
            "embedder_options": {"dimension": 256},
            "chunk_size": 500,
        }
    )
    assert response["ok"] is True
    assert captured["parser"] == "docling"
    assert captured["pipeline_options"] == {"chunk_size": 2000, "ocr_mode": "auto"}
    assert captured["embedder_options"] == {"dimension": 256}
    assert captured["chunk_size"] == 500


def test_plugin_host_unknown_action():
    response = handle({"id": "bad", "action": "answer"})
    assert response["ok"] is False
    assert "Unknown action" in response["error"]


def test_plugin_host_cancel_token_aborts_convert(tmp_path):
    pdf = tmp_path / "manual.pdf"
    make_pdf(pdf)
    cancel = CancellationToken()
    cancel.cancel()
    response = handle(
        {
            "id": "convert",
            "action": "convert",
            "input": str(pdf),
            "output": str(tmp_path / "out.vera"),
        },
        cancel=cancel,
    )
    assert response["ok"] is False
    assert response.get("cancelled") is True


def test_plugin_host_skip_token_aborts_current_file(tmp_path):
    pdf = tmp_path / "manual.pdf"
    make_pdf(pdf)
    cancel = CancellationToken()
    cancel.skip()
    response = handle(
        {
            "id": "convert",
            "action": "convert",
            "input": str(pdf),
            "output": str(tmp_path / "out.vera"),
        },
        cancel=cancel,
    )
    assert response["ok"] is False
    assert response.get("cancelled") is True
    assert "skip" in response["error"].lower()


def test_plugin_host_emits_conversion_progress(monkeypatch, tmp_path):
    events: list[dict] = []

    def fake_convert(source_path, output_path, **options):
        return str(output_path)

    monkeypatch.setattr("vera_plugin_host.worker.convert", fake_convert)
    result = handle_convert(
        {
            "id": "convert",
            "action": "convert",
            "input": str(tmp_path / "manual.pdf"),
            "output": str(tmp_path / "out.vera"),
        },
        write_event=events.append,
    )
    assert result["output"].endswith("out.vera")
    assert [event["event"] for event in events] == ["conversion_progress", "conversion_progress"]
    assert events[0]["completed"] == 0
    assert events[1]["completed"] == 1


def _plugin_host_env() -> dict[str, str]:
    return {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            [
                str(ROOT / "packages" / "vera-app" / "src"),
                str(ROOT / "packages" / "vera-ingest" / "src"),
                str(ROOT / "packages" / "vera-ingest-pymupdf" / "src"),
                str(ROOT / "packages" / "vera-doc" / "src"),
            ]
        ),
        "PYTHONUNBUFFERED": "1",
    }


def test_plugin_host_stdio_ping_roundtrip():
    proc = subprocess.Popen(
        [sys.executable, "-m", "vera_plugin_host"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_plugin_host_env(),
    )
    try:
        assert proc.stdin is not None
        assert proc.stdout is not None
        proc.stdin.write(json.dumps({"id": "1", "action": "ping"}) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        payload = json.loads(line)
        assert payload["ok"] is True
        assert payload["result"]["protocol"] == 2
        assert "pymupdf" in payload["result"]["pipelines"]
        assert "hashing" in payload["result"]["embedders"]
    finally:
        proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=5)


def test_plugin_host_embed_and_info_use_hashing():
    info = handle({"id": "info", "action": "embedder_info", "model": "hashing"})
    assert info["ok"] is True, info
    assert info["result"]["dimension"] > 0
    embed = handle(
        {
            "id": "embed",
            "action": "embed",
            "model": "hashing",
            "texts": ["stormwater detention"],
        }
    )
    assert embed["ok"] is True, embed
    assert len(embed["result"]["vectors"]) == 1
    assert embed["result"]["dimension"] == info["result"]["dimension"]


def test_plugin_host_describe_embedding_providers():
    response = handle({"id": "desc", "action": "describe_embedding_providers"})
    assert response["ok"] is True
    providers = {item["provider"] for item in response["result"]["providers"]}
    assert "hashing" in providers


def test_plugin_host_stdio_malformed_request():
    proc = subprocess.Popen(
        [sys.executable, "-m", "vera_plugin_host"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_plugin_host_env(),
    )
    try:
        assert proc.stdin is not None
        assert proc.stdout is not None
        proc.stdin.write("not-json\n")
        proc.stdin.flush()
        payload = json.loads(proc.stdout.readline())
        assert payload["ok"] is False
        assert payload["id"] is None
    finally:
        proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=5)


def test_plugin_host_embed_rejects_empty_or_missing_texts():
    empty = handle({"id": "embed", "action": "embed", "model": "hashing", "texts": []})
    assert empty["ok"] is False
    assert "texts" in empty["error"]
    missing = handle({"id": "embed", "action": "embed", "model": "hashing"})
    assert missing["ok"] is False
    assert "texts" in missing["error"]


def test_plugin_host_list_embedding_models_requires_provider():
    missing = handle({"id": "models", "action": "list_embedding_models"})
    assert missing["ok"] is False
    assert "provider is required" in missing["error"]
    hashing = handle({"id": "models", "action": "list_embedding_models", "provider": "hashing"})
    assert hashing["ok"] is True, hashing
    assert hashing["result"]["provider"] == "hashing"
    assert hashing["result"]["models"]


def test_plugin_host_preflight_hashing():
    response = handle({"id": "pf", "action": "preflight_embedder", "model": "hashing"})
    assert response["ok"] is True, response
    assert response["result"]["ok"] is True


def test_plugin_host_embed_honors_cancel():
    cancel = CancellationToken()
    cancel.cancel()
    response = handle(
        {
            "id": "embed",
            "action": "embed",
            "model": "hashing",
            "texts": ["stormwater detention"],
        },
        cancel=cancel,
    )
    assert response["ok"] is False
    assert response.get("cancelled") is True
    assert "Embedding cancelled" in response["error"]
