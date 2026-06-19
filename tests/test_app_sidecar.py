from test_convert_search import make_pdf
from vera import convert
from vera_app.sidecar import handle


def test_source_action_returns_pdf_data_url(tmp_path):
    pdf = tmp_path / "manual.pdf"
    out = tmp_path / "manual.vera"
    make_pdf(pdf)
    convert(str(pdf), str(out), model="hashing", store_original=True)

    response = handle({"id": "1", "action": "source", "path": str(out)})

    assert response["ok"] is True
    result = response["result"]
    assert result["filename"] == "manual.pdf"
    assert result["mime_type"] == "application/pdf"
    assert result["size"] > 0
    assert result["hash"]
    assert result["data_url"].startswith("data:application/pdf;base64,")


def test_answer_action_returns_cited_evidence(tmp_path):
    pdf = tmp_path / "manual.pdf"
    out = tmp_path / "manual.vera"
    make_pdf(pdf)
    convert(str(pdf), str(out), model="hashing", store_original=True)

    response = handle({"id": "1", "action": "answer", "path": str(out), "prompt": "restaurant parking", "mode": "keyword", "top_k": 1})

    assert response["ok"] is True
    result = response["result"]
    assert "[C1]" in result["answer"]
    assert result["citations"][0]["id"] == "C1"
    assert "parking" in result["citations"][0]["result"]["text"].lower()
    assert result["citations"][0]["result"]["regions"]
    assert "Answer the user" in result["llm_prompt"]
