from __future__ import annotations

import json

from vera_app.llm import LlmConfig, chat


TOOL = {
    "type": "function",
    "function": {
        "name": "search",
        "description": "Search documents",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
}


class FakeResponse:
    def __init__(self, payload=None, lines=None):
        self.payload = payload
        self.lines = lines or []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()

    def __iter__(self):
        return iter(self.lines)


def config(**overrides):
    values = {
        "provider": "openai_compatible",
        "provider_key": "openai",
        "model": "gpt-5.6-sol",
        "base_url": "https://api.openai.com/v1",
        "reasoning_effort": "medium",
    }
    values.update(overrides)
    return LlmConfig(**values)


def test_gpt_56_uses_responses_and_replays_reasoning(monkeypatch):
    requests = []
    responses = [
        {
            "id": "resp_1",
            "model": "gpt-5.6-sol",
            "output": [
                {"type": "reasoning", "id": "rs_1", "encrypted_content": "encrypted"},
                {
                    "type": "function_call",
                    "id": "fc_1",
                    "call_id": "call_1",
                    "name": "search",
                    "arguments": '{"query":"stormwater"}',
                },
            ],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        },
        {
            "id": "resp_2",
            "model": "gpt-5.6-sol",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "Final answer."}],
                }
            ],
        },
    ]

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return FakeResponse(payload=responses.pop(0))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    first = chat([{"role": "user", "content": "Find it"}], config(), tools=[TOOL])
    assert first.tool_calls[0].name == "search"
    assert first.tool_calls[0].arguments == {"query": "stormwater"}
    assert first.message["_responses_items"][0]["type"] == "reasoning"

    request, _ = requests[0]
    body = json.loads(request.data)
    assert request.full_url == "https://api.openai.com/v1/responses"
    assert body["store"] is False
    assert body["include"] == ["reasoning.encrypted_content"]
    assert body["reasoning"] == {"effort": "medium"}
    assert body["tools"][0]["name"] == "search"
    assert "function" not in body["tools"][0]

    second = chat(
        [
            {"role": "user", "content": "Find it"},
            first.message,
            {"role": "tool", "tool_call_id": "call_1", "content": '{"hits": 2}'},
        ],
        config(),
        tools=[TOOL],
    )
    assert second.content == "Final answer."
    replay = json.loads(requests[1][0].data)["input"]
    assert any(item.get("type") == "reasoning" for item in replay)
    assert any(item.get("type") == "function_call" for item in replay)
    assert {"type": "function_call_output", "call_id": "call_1", "output": '{"hits": 2}'} in replay


def test_gpt_56_responses_streams_text(monkeypatch):
    completed = {
        "id": "resp_stream",
        "model": "gpt-5.6-terra",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Hello world"}],
            }
        ],
    }
    events = [
        b'data: {"type":"response.output_text.delta","delta":"Hello "}\n',
        b'data: {"type":"response.output_text.delta","delta":"world"}\n',
        f"data: {json.dumps({'type': 'response.completed', 'response': completed})}\n".encode(),
        b"data: [DONE]\n",
    ]

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda _request, timeout: FakeResponse(lines=events),
    )
    deltas = []
    response = chat(
        [{"role": "user", "content": "Say hello"}],
        config(model="gpt-5.6-terra"),
        on_delta=deltas.append,
    )
    assert deltas == ["Hello ", "world"]
    assert response.content == "Hello world"
