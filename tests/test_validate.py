import sqlite3
import subprocess
import sys

import numpy as np

from vera import VeraDocument
from vera_ingest import convert
from test_convert_search import make_pdf


def test_validate_passes_for_converted_vera(tmp_path):
    pdf = tmp_path / "ordinance.pdf"
    out = tmp_path / "ordinance.vera"
    make_pdf(pdf)
    convert(str(pdf), str(out), model="hashing", chunk_size=40, overlap=5)

    doc = VeraDocument.open(str(out))
    report = doc.validate()
    doc.close()

    assert report["ok"] is True
    assert report["issues"] == []
    assert report["counts"]["chunks"] >= 1
    assert report["counts"]["embeddings"] == report["counts"]["chunks"]
    assert report["checks"]["original_document_present"] is True


def test_validate_reports_missing_required_metadata(tmp_path):
    pdf = tmp_path / "ordinance.pdf"
    out = tmp_path / "ordinance.vera"
    make_pdf(pdf)
    convert(str(pdf), str(out), model="hashing")
    conn = sqlite3.connect(out)
    conn.execute("DELETE FROM vera_metadata WHERE key='format_version'")
    conn.commit()
    conn.close()

    doc = VeraDocument.open(str(out))
    report = doc.validate()
    doc.close()

    assert report["ok"] is False
    assert any("Missing required metadata key: format_version" in issue for issue in report["issues"])


def test_validate_reports_bad_embedding_dimension(tmp_path):
    pdf = tmp_path / "ordinance.pdf"
    out = tmp_path / "ordinance.vera"
    make_pdf(pdf)
    convert(str(pdf), str(out), model="hashing")
    conn = sqlite3.connect(out)
    conn.execute(
        "UPDATE embeddings SET vector = ? WHERE chunk_id = 'chunk_000001'",
        (b"bad",),
    )
    conn.commit()
    conn.close()

    doc = VeraDocument.open(str(out))
    report = doc.validate()
    doc.close()

    assert report["ok"] is False
    assert any("Invalid embedding blob" in issue for issue in report["issues"])


def test_validate_reports_vector_that_violates_l2_policy(tmp_path):
    out = tmp_path / "normalization.vera"
    with VeraDocument.create(out) as doc:
        doc.add([])

    conn = sqlite3.connect(out)
    vector = np.zeros(384, dtype="<f4")
    vector[0] = 2.0
    conn.execute(
        """
        INSERT INTO chunks(chunk_id, text, metadata_json, created_at, updated_at)
        VALUES ('bad', 'Bad vector', '{}', '', '')
        """
    )
    conn.execute(
        """
        INSERT INTO embeddings(
            chunk_id, model_name, model_dimension, vector, vector_format, created_at
        ) VALUES ('bad', 'vera-hashing-384', 384, ?, 'float32_le', '')
        """,
        (vector.tobytes(),),
    )
    conn.execute("INSERT INTO chunks_fts(chunk_id, text) VALUES ('bad', 'Bad vector')")
    conn.commit()
    conn.close()

    with VeraDocument.open(out) as doc:
        report = doc.validate()

    assert report["ok"] is False
    assert any("not L2-normalized" in issue for issue in report["issues"])


def test_validate_treats_missing_normalization_metadata_as_unknown(tmp_path):
    out = tmp_path / "legacy.vera"
    with VeraDocument.create(out):
        pass
    conn = sqlite3.connect(out)
    conn.execute(
        "DELETE FROM vera_metadata WHERE key='default_embedding_normalization'"
    )
    conn.commit()
    conn.close()

    with VeraDocument.open(out) as doc:
        assert doc.inspect()["default_embedding_normalization"] == "unknown"
        assert doc.validate()["ok"] is True


def test_validate_rejects_noncanonical_normalization_value(tmp_path):
    out = tmp_path / "noncanonical.vera"
    with VeraDocument.create(out):
        pass
    conn = sqlite3.connect(out)
    conn.execute(
        """
        UPDATE vera_metadata SET value = 'L2'
        WHERE key = 'default_embedding_normalization'
        """
    )
    conn.commit()
    conn.close()

    with VeraDocument.open(out) as doc:
        report = doc.validate()

    assert report["ok"] is False
    assert any(
        "Invalid default_embedding_normalization" in issue
        for issue in report["issues"]
    )


def test_validate_warns_when_original_was_intentionally_omitted(tmp_path):
    pdf = tmp_path / "ordinance.pdf"
    out = tmp_path / "ordinance.vera"
    make_pdf(pdf)
    convert(str(pdf), str(out), model="hashing", store_original=False)

    doc = VeraDocument.open(str(out))
    report = doc.validate()
    doc.close()

    assert report["ok"] is True
    assert "Original document asset is missing" in report["warnings"]


def test_cli_validate_outputs_pass(tmp_path):
    pdf = tmp_path / "manual.pdf"
    out = tmp_path / "manual.vera"
    make_pdf(pdf)
    convert(str(pdf), str(out), model="hashing")

    result = subprocess.run(
        [sys.executable, "-m", "vera_cli", "validate", str(out)],
        text=True,
        capture_output=True,
        check=True,
    )

    assert "VERA validation: PASS" in result.stdout
    assert "Issues: 0" in result.stdout
