from __future__ import annotations

import io
import json
import threading
import time
import urllib.error

import pytest

from vera_app.cancellation import CancellationToken, CancelledError
from vera_app.llm import (
    LlmConfig,
    ProviderHttpError,
    VisionUnsupportedError,
    _consume_stream,
    _encode_json_payload,
    _extract_xml_tool_calls,
    chat,
)

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


def test_extracts_xml_tool_calls():
    content = (
        "<tool_call>search<arg_key>query</arg_key><arg_value>first query</arg_value>"
        "<arg_key>mode</arg_key><arg_value>keyword</arg_value>"
        "<arg_key>top_k</arg_key><arg_value>10</arg_value></tool_call>"
        "<tool_call>search<arg_key>query</arg_key><arg_value>second query</arg_value>"
        "<arg_key>mode</arg_key><arg_value>keyword</arg_value>"
        "<arg_key>top_k</arg_key><arg_value>10</arg_value></tool_call>"
    )

    cleaned, calls = _extract_xml_tool_calls(content)

    assert cleaned == ""
    assert [call.name for call in calls] == ["search", "search"]
    assert calls[0].arguments == {"query": "first query", "mode": "keyword", "top_k": 10}
    assert calls[1].arguments["query"] == "second query"


def test_strips_malformed_nested_xml_tool_call_before_answer():
    content = (
        '<tool_call>search】query: "Table 2-2c" mode: keyword'
        '<tool_call>search】query: "Table 2-2d"</arg_value>'
        "<arg_key>mode</arg_key><arg_value>keyword</arg_value>"
        "<arg_key>top_k</arg_key><arg_value>10</arg_value></tool_call>"
        "Below is the grounded answer. [C9]"
    )

    cleaned, calls = _extract_xml_tool_calls(content)

    assert cleaned == "Below is the grounded answer. [C9]"
    assert [call.name for call in calls] == ["search"]
    assert calls[0].arguments == {"mode": "keyword", "top_k": 10}


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


def test_stream_stops_before_emitting_more_deltas():
    cancel = CancellationToken()
    cancel.cancel()

    with pytest.raises(CancelledError):
        _consume_stream(
            FakeResponse(lines=[b'data: {"choices":[{"delta":{"content":"late"}}]}\n']),
            lambda _text: pytest.fail("cancelled stream emitted a delta"),
            cancel,
        )


def test_stream_normalizes_response_close_race():
    class ClosingResponse:
        def __iter__(self):
            raise AttributeError("'NoneType' object has no attribute 'peek'")

    cancel = CancellationToken()
    cancel.cancel()

    with pytest.raises(CancelledError):
        _consume_stream(ClosingResponse(), lambda _text: None, cancel)


def test_request_cancels_while_waiting_for_provider_headers(monkeypatch):
    opened = threading.Event()
    release = threading.Event()
    cancel = CancellationToken()

    def fake_urlopen(_request, timeout):
        opened.set()
        release.wait(timeout)
        return FakeResponse(payload={"choices": [{"message": {"content": "too late"}}]})

    monkeypatch.setattr("vera_app.llm.urllib.request.urlopen", fake_urlopen)
    timer = threading.Timer(0.05, cancel.cancel)
    timer.start()
    started = time.monotonic()
    try:
        with pytest.raises(CancelledError):
            chat([{"role": "user", "content": "Find it"}], config(), cancel=cancel)
    finally:
        release.set()
        timer.cancel()

    assert opened.is_set()
    assert time.monotonic() - started < 1


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


def test_json_payload_replaces_unpaired_utf16_surrogates():
    payload = {
        "input": [
            {
                "content": [
                    {"type": "input_text", "text": "Extracted text \ud800 continues"},
                ],
            },
        ],
    }

    encoded = _encode_json_payload(payload)

    assert b"\xed\xa0\x80" not in encoded
    assert (
        json.loads(encoded)["input"][0]["content"][0]["text"] == "Extracted text \ufffd continues"
    )


def test_provider_http_error_uses_bounded_message(monkeypatch):
    provider_payload = {
        "error": {
            "message": "This request requires more credits, or fewer max_tokens.",
            "code": 402,
            "metadata": {
                "previous_errors": [{"message": "repeated provider detail"}] * 50,
            },
        },
        "user_id": "provider-user-id",
    }

    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            402,
            "Payment Required",
            {},
            io.BytesIO(json.dumps(provider_payload).encode()),
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(ProviderHttpError) as raised:
        chat(
            [{"role": "user", "content": "Find it"}],
            config(
                provider_key="openrouter",
                model="anthropic/claude-sonnet",
                base_url="https://openrouter.ai/api/v1",
            ),
        )

    message = str(raised.value)
    assert raised.value.status_code == 402
    assert "requires more credits" in message
    assert "Add provider credits or choose a lower-cost model." in message
    assert "previous_errors" not in message
    assert "provider-user-id" not in message
    assert len(message) < 500


def test_openrouter_404_without_image_endpoint_is_vision_unsupported(monkeypatch):
    provider_payload = {
        "error": {
            "message": "No endpoints found that support image input",
            "code": 404,
        },
    }

    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            404,
            "Not Found",
            {},
            io.BytesIO(json.dumps(provider_payload).encode()),
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(VisionUnsupportedError):
        chat(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe this image"},
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA=="}},
                    ],
                }
            ],
            config(
                provider_key="openrouter",
                model="z-ai/glm-5.2",
                base_url="https://openrouter.ai/api/v1",
            ),
        )


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
