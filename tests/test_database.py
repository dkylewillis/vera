from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from vera import (
    AttachmentRecord,
    AttachmentRef,
    ChunkRecord,
    DuplicateRecordError,
    ReadOnlyError,
    VeraDocument,
)


def test_database_chunk_crud_and_search(tmp_path: Path) -> None:
    path = tmp_path / "records.vera"
    with VeraDocument.create(path, metadata={"project": "test"}) as database:
        database.add(
            [
                ChunkRecord(
                    id="one",
                    text="Stormwater detention pond requirements.",
                    metadata={"page": 12, "kind": "design"},
                ),
                ChunkRecord(
                    id="two",
                    text="Unrelated landscaping guidance.",
                    metadata={"page": 42, "kind": "landscape"},
                ),
            ]
        )
        assert database.metadata == {"project": "test"}
        assert [item.id for item in database.get(where={"kind": "design"})] == [
            "one"
        ]
        assert database.search(text="detention requirements", top_k=1)[
            0
        ].record.id == "one"

        database.upsert(
            [
                ChunkRecord(
                    id="one",
                    text="Updated detention storage requirements.",
                    metadata={"page": 13, "kind": "design"},
                )
            ]
        )
        assert database.get(["one"])[0].metadata["page"] == 13
        assert database.delete(["two"]) == 1
        assert database.validate()["ok"] is True

    with VeraDocument.open(path) as database:
        assert [item.id for item in database.get()] == ["one"]
        with pytest.raises(ReadOnlyError):
            database.delete(["one"])


def test_database_attachments_and_references(tmp_path: Path) -> None:
    path = tmp_path / "attachments.vera"
    attachment = AttachmentRecord(
        id="source",
        data=b"%PDF example",
        media_type="application/pdf",
        filename="source.pdf",
    )
    with VeraDocument.create(path) as database:
        database.put_attachments([attachment])
        database.add(
            [
                ChunkRecord(
                    id="chunk",
                    text="A source-backed chunk.",
                    attachments=(AttachmentRef("source", role="source"),),
                )
            ]
        )
        stored = database.get_attachment("source")
        assert stored.data == attachment.data
        assert database.get(["chunk"])[0].attachments == (
            AttachmentRef("source", role="source"),
        )
        with pytest.raises(ValueError, match="referenced"):
            database.delete_attachment("source")


def test_database_batches_are_atomic(tmp_path: Path) -> None:
    path = tmp_path / "atomic.vera"
    with VeraDocument.create(path) as database:
        database.add([ChunkRecord(id="existing", text="First")])
        with pytest.raises(DuplicateRecordError):
            database.add(
                [
                    ChunkRecord(id="new", text="Would otherwise be inserted"),
                    ChunkRecord(id="existing", text="Duplicate"),
                ]
            )
        assert [item.id for item in database.get()] == ["existing"]


def test_transaction_rolls_back(tmp_path: Path) -> None:
    path = tmp_path / "transaction.vera"
    with VeraDocument.create(path) as database:
        with pytest.raises(RuntimeError):
            with database.transaction():
                database.add([ChunkRecord(id="temporary", text="Temporary")])
                raise RuntimeError("stop")
        assert database.get() == []


def test_chunk_and_attachment_validation() -> None:
    with pytest.raises(ValueError, match="text"):
        ChunkRecord(id="empty", text=" ")
    with pytest.raises(ValueError, match="finite"):
        ChunkRecord(id="bad-vector", text="Text", vector=[float("nan")])
    with pytest.raises(TypeError, match="JSON"):
        ChunkRecord(id="bad-metadata", text="Text", metadata={"bad": object()})
    with pytest.raises(ValueError, match="checksum"):
        AttachmentRecord(
            id="bad",
            data=b"content",
            media_type="text/plain",
            checksum="not-the-hash",
        )


class TinyEmbedder:
    model_name = "test/tiny"
    dimension = 2

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.asarray(
            [
                [1.0, 0.0] if "alpha" in text.lower() else [0.0, 1.0]
                for text in texts
            ],
            dtype=np.float32,
        )


def test_precomputed_vectors_and_dimension_validation(tmp_path: Path) -> None:
    path = tmp_path / "vectors.vera"
    embedder = TinyEmbedder()
    with VeraDocument.create(
        path,
        embedding_function=embedder,
    ) as database:
        database.add(
            [
                ChunkRecord(id="alpha", text="Alpha text"),
                ChunkRecord(id="beta", text="Beta text", vector=[0.0, 1.0]),
            ]
        )
        assert database.search(
            vector=[1.0, 0.0],
            mode="semantic",
            top_k=1,
        )[0].record.id == "alpha"
        with pytest.raises(ValueError, match="dimension"):
            database.add(
                [ChunkRecord(id="bad", text="Bad", vector=[1.0, 2.0, 3.0])]
            )


def test_empty_database_is_valid(tmp_path: Path) -> None:
    with VeraDocument.create(tmp_path / "empty.vera") as database:
        assert database.validate()["ok"] is True
        assert database.inspect()["chunks"] == 0

