"""Descriptor discovery must work when the Docling runtime is missing."""

from __future__ import annotations

import pytest

from vera_ingest import UnknownIngestPipelineError
from vera_ingest_docling import create_descriptor, create_pipeline
from vera_ingest_docling.options import describe_pipeline


def test_describe_pipeline_advertises_docling_without_runtime(monkeypatch):
    monkeypatch.setattr(
        "vera_ingest_docling.options._docling_runtime_available",
        lambda: False,
    )
    descriptor = describe_pipeline()
    assert descriptor.provider == "docling"
    assert descriptor.spec == "docling"
    assert descriptor.installed is False
    assert {field.key for field in descriptor.fields} == {
        "chunk_size",
        "ocr_mode",
        "ocr_language",
        "pdf_backend",
    }


def test_create_descriptor_entry_point_does_not_need_runtime(monkeypatch):
    monkeypatch.setattr(
        "vera_ingest_docling.options._docling_runtime_available",
        lambda: False,
    )
    descriptor = create_descriptor()
    assert descriptor.installed is False


def test_create_pipeline_explains_missing_runtime(monkeypatch):
    # create_pipeline() binds this helper at import time in __init__.py.
    monkeypatch.setattr(
        "vera_ingest_docling._docling_runtime_available",
        lambda: False,
    )
    with pytest.raises(UnknownIngestPipelineError, match="vera-ingest-docling"):
        create_pipeline()
