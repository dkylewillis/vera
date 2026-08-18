"""Offline checks for Docling artifacts completeness (no Docling runtime).

Incomplete Hugging Face snapshots must stay online so the next run can resume.
Treating a partial cache as ready locks Convert into offline mode and fails.
"""

from __future__ import annotations

from pathlib import Path

from vera_ingest_docling.converter import (
    _LAYOUT_MODEL_DIR,
    _TABLEFORMER_MODEL_DIR,
    _docling_models_ready,
    _layout_model_cached,
    _prepare_hub_download,
    _tableformer_cached,
    ensure_docling_models,
)


def _write_complete_docling_artifacts(root: Path) -> None:
    heron = root / _LAYOUT_MODEL_DIR
    heron.mkdir(parents=True, exist_ok=True)
    (heron / "config.json").write_text("{}", encoding="utf-8")
    (heron / "model.onnx").write_bytes(b"weights")
    table = root / _TABLEFORMER_MODEL_DIR / "model_artifacts" / "tableformer" / "accurate"
    table.mkdir(parents=True, exist_ok=True)
    (table / "tm_config.json").write_text("{}", encoding="utf-8")


def test_incomplete_huggingface_download_is_not_cached(tmp_path: Path):
    _write_complete_docling_artifacts(tmp_path)
    incomplete = tmp_path / _LAYOUT_MODEL_DIR / "model.onnx.incomplete"
    incomplete.write_bytes(b"partial")

    assert _layout_model_cached(tmp_path) is False
    assert _docling_models_ready(tmp_path) is False


def test_zero_byte_layout_weights_are_not_cached(tmp_path: Path):
    _write_complete_docling_artifacts(tmp_path)
    (tmp_path / _LAYOUT_MODEL_DIR / "model.onnx").write_bytes(b"")

    assert _layout_model_cached(tmp_path) is False
    assert _docling_models_ready(tmp_path) is False


def test_tableformer_incomplete_download_keeps_cache_online(tmp_path: Path):
    _write_complete_docling_artifacts(tmp_path)
    table_root = tmp_path / _TABLEFORMER_MODEL_DIR
    (table_root / "tm_config.json.incomplete").write_bytes(b"partial")

    assert _layout_model_cached(tmp_path) is True
    assert _tableformer_cached(tmp_path) is False
    assert _docling_models_ready(tmp_path) is False


def test_ensure_docling_models_reports_missing_artifacts_path(monkeypatch):
    monkeypatch.delenv("DOCLING_ARTIFACTS_PATH", raising=False)
    result = ensure_docling_models()
    assert result == {"ready": False, "downloaded": False, "reason": "no_artifacts_path"}


def test_blank_artifacts_path_is_treated_as_missing(monkeypatch):
    monkeypatch.setenv("DOCLING_ARTIFACTS_PATH", "   ")
    result = ensure_docling_models()
    assert result["reason"] == "no_artifacts_path"
    assert result["ready"] is False


def test_prepare_hub_download_is_safe_to_call_twice():
    _prepare_hub_download()
    _prepare_hub_download()


def test_download_docling_models_prints_progress_and_runs_snapshot(monkeypatch, tmp_path, capsys):
    from vera_ingest_docling import converter as converter_mod

    seen = {}

    def fake_snapshot(artifacts):
        seen["path"] = artifacts

    monkeypatch.setattr(converter_mod, "_run_docling_snapshot_download", fake_snapshot)
    converter_mod._download_docling_models(tmp_path)

    assert seen["path"] == tmp_path
    err = capsys.readouterr().err
    assert "380 MB" in err
    assert "finished" in err


def test_run_docling_snapshot_download_fetches_onnx_layout_and_accurate_tables(
    monkeypatch, tmp_path
):
    from vera_ingest_docling import converter as converter_mod

    calls = []

    def fake_download(repo_id, local_dir, allow_patterns=None):
        calls.append(
            {
                "repo_id": repo_id,
                "local_dir": local_dir,
                "allow_patterns": allow_patterns,
            }
        )

    monkeypatch.setattr(converter_mod, "_download_hf_snapshot", fake_download)
    converter_mod._run_docling_snapshot_download(tmp_path)

    assert [item["repo_id"] for item in calls] == [
        "docling-project/docling-layout-heron-onnx",
        "docling-project/docling-models",
    ]
    assert calls[1]["allow_patterns"] == converter_mod._TABLEFORMER_ALLOW_PATTERNS


def test_run_docling_snapshot_download_skips_complete_cache(monkeypatch, tmp_path):
    from vera_ingest_docling import converter as converter_mod

    _write_complete_docling_artifacts(tmp_path)
    monkeypatch.setattr(
        converter_mod,
        "_download_hf_snapshot",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("complete cache must not download")
        ),
    )
    converter_mod._run_docling_snapshot_download(tmp_path)
