import json

from test_convert_search import make_pdf
from vera import convert
from vera_app.llm import ChatResponse, LlmConfig, ToolCall, ToolsUnsupportedError
from vera_app.sidecar import handle


def _llm_payload():
    return {
        "provider": "openai_compatible",
        "model": "test-model",
        "base_url": "http://localhost:1234/v1",
    }


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


def test_answer_action_requires_llm(tmp_path):
    pdf = tmp_path / "manual.pdf"
    out = tmp_path / "manual.vera"
    make_pdf(pdf)
    convert(str(pdf), str(out), model="hashing", store_original=True)

    response = handle({"id": "1", "action": "answer", "path": str(out), "prompt": "restaurant parking"})

    assert response["ok"] is False
    assert "model must be selected" in response["error"].lower()


def test_answer_action_runs_agentic_search(tmp_path, monkeypatch):
    pdf = tmp_path / "manual.pdf"
    out = tmp_path / "manual.vera"
    make_pdf(pdf)
    convert(str(pdf), str(out), model="hashing", store_original=True)

    calls = {"n": 0}

    def fake_chat(messages, config, tools=None, tool_choice="auto"):
        calls["n"] += 1
        if calls["n"] == 1:
            assert tools, "tools should be offered on the first turn"
            assert config.model == "test-model"
            return ChatResponse(
                content="",
                tool_calls=[ToolCall(id="call_1", name="search", arguments={"query": "restaurant parking", "mode": "keyword", "top_k": 1})],
                message={"role": "assistant", "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "search", "arguments": "{}"}}]},
                model="test-model",
                usage=None,
            )
        joined = json.dumps(messages)
        assert "C1" in joined, "tool result with citation should be fed back to the model"
        assert "parking" in joined.lower()
        return ChatResponse(
            content="Restaurant parking requirements are in the cited passage. [C1]",
            tool_calls=[],
            message={"role": "assistant", "content": "done"},
            model="test-model",
            usage={"total_tokens": 42},
        )

    monkeypatch.setattr("vera_app.sidecar.chat", fake_chat)

    response = handle({"id": "1", "action": "answer", "path": str(out), "prompt": "restaurant parking", "llm": _llm_payload()})

    assert response["ok"] is True
    result = response["result"]
    assert result["answer_mode"] == "agent"
    assert result["answer"].endswith("[C1]")
    assert result["citations"][0]["id"] == "C1"
    assert result["citations"][0]["result"]["regions"]
    assert result["searches"][0]["query"] == "restaurant parking"
    assert result["llm"]["model"] == "test-model"


def test_answer_action_merges_custom_instructions(tmp_path, monkeypatch):
    pdf = tmp_path / "manual.pdf"
    out = tmp_path / "manual.vera"
    make_pdf(pdf)
    convert(str(pdf), str(out), model="hashing", store_original=True)

    seen = {}

    def fake_chat(messages, config, tools=None, tool_choice="auto"):
        seen["system"] = messages[0]["content"]
        return ChatResponse(
            content="Answer.",
            tool_calls=[],
            message={"role": "assistant", "content": "Answer."},
            model="test-model",
            usage=None,
        )

    monkeypatch.setattr("vera_app.sidecar.chat", fake_chat)

    response = handle({
        "id": "1",
        "action": "answer",
        "path": str(out),
        "prompt": "restaurant parking",
        "instructions": "Respond as a compliance checklist.",
        "llm": _llm_payload(),
    })

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

    def fake_chat(messages, config, tools=None, tool_choice="auto"):
        raise ToolsUnsupportedError("this model does not support tools")

    def fake_generate(messages, config):
        assert "restaurant parking" in messages[-1]["content"]
        assert "[C1]" in messages[-1]["content"]

        class Result:
            answer = "Parking is covered in the cited passage. [C1]"
            provider = "openai_compatible"
            model = "test-model"
            usage = {"total_tokens": 7}

        return Result()

    monkeypatch.setattr("vera_app.sidecar.chat", fake_chat)
    monkeypatch.setattr("vera_app.sidecar.generate", fake_generate)

    response = handle({"id": "1", "action": "answer", "path": str(out), "prompt": "restaurant parking", "llm": _llm_payload()})

    assert response["ok"] is True
    result = response["result"]
    assert result["answer_mode"] == "retrieval"
    assert result["answer"].endswith("[C1]")
    assert result["citations"][0]["id"] == "C1"


def test_list_modes_action_returns_builtin_modes():
    response = handle({"id": "1", "action": "list_modes"})

    assert response["ok"] is True
    ids = {mode["id"] for mode in response["result"]["modes"]}
    assert {"ask", "research", "summarize"} <= ids


def test_llm_config_accepts_injected_api_key():
    config = LlmConfig.from_request({
        "provider": "openai_compatible",
        "model": "gpt-4o-mini",
        "base_url": "https://api.openai.com/v1",
        "auth_type": "api_key",
        "api_key": "secret-key",
    })

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

    response = handle({
        "id": "1",
        "action": "list_models",
        "llm": {
            "provider": "openai_compatible",
            "base_url": "https://api.openai.com/v1",
            "auth_type": "api_key",
            "api_key": "secret-key",
        },
    })

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

    payloads = iter([
        {"data": [{"id": "b-model"}, {"id": "a-model"}, {"id": "a-model"}]},
        {"models": [{"name": "llama3.1"}, {"name": "qwen2"}]},
    ])

    def fake_urlopen(request, timeout=None):
        return FakeResponse(next(payloads))

    monkeypatch.setattr(llm_module.urllib.request, "urlopen", fake_urlopen)

    openai_config = LlmConfig.from_request({"base_url": "https://api.openai.com/v1", "auth_type": "none"})
    assert llm_module.list_models(openai_config) == ["a-model", "b-model"]

    ollama_config = LlmConfig.from_request({"base_url": "http://localhost:11434/v1", "auth_type": "none"})
    assert llm_module.list_models(ollama_config) == ["llama3.1", "qwen2"]
