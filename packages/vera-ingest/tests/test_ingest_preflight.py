"""Ingest pipeline credential preflight."""

from vera_ingest.descriptors import PipelineCapabilities, PipelineDescriptor
from vera_ingest.pipeline import (
    preflight_ingest_pipeline,
    register_ingest_pipeline,
    register_ingest_pipeline_descriptor,
    reset_ingest_pipeline_registry,
)


def test_pymupdf_preflight_does_not_require_a_key():
    result = preflight_ingest_pipeline("pymupdf")
    assert result.ok is True
    assert result.missing_credential_env == ""


def test_preflight_reports_a_missing_pipeline_credential(monkeypatch):
    monkeypatch.delenv("UNIT_PIPELINE_KEY", raising=False)

    def descriptor(variant: str = "default") -> PipelineDescriptor:
        del variant
        return PipelineDescriptor(
            provider="needs-key",
            variant="",
            spec="needs-key",
            label="needs key",
            capabilities=PipelineCapabilities(
                requires_api_key=True,
                credential_env="UNIT_PIPELINE_KEY",
                source_formats=("pdf",),
            ),
        )

    register_ingest_pipeline(
        "needs-key",
        lambda variant="default": (lambda source_path, request: None),
        replace=True,
    )
    register_ingest_pipeline_descriptor("needs-key", descriptor, replace=True)
    try:
        missing = preflight_ingest_pipeline("needs-key")
        assert missing.ok is False
        assert missing.missing_credential_env == "UNIT_PIPELINE_KEY"
        monkeypatch.setenv("UNIT_PIPELINE_KEY", "present")
        assert preflight_ingest_pipeline("needs-key").ok is True
    finally:
        reset_ingest_pipeline_registry()
