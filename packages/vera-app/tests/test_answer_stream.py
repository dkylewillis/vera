"""Incremental Ask streaming must never leak inline tool-call markup."""

from __future__ import annotations

from vera_app.chat import AnswerStream
from vera_app.llm import ChatResponse, ToolCall


def _response(content: str, tool_calls: list[ToolCall] | None = None) -> ChatResponse:
    return ChatResponse(
        content=content,
        tool_calls=tool_calls or [],
        message={"role": "assistant", "content": content},
        model="test-model",
    )


def _stream() -> tuple[AnswerStream, list[dict]]:
    events: list[dict] = []
    return AnswerStream(events.append), events


def _delta_text(events: list[dict]) -> str:
    return "".join(event.get("text", "") for event in events if event.get("event") == "answer_delta")


def test_withholds_partial_functions_marker_then_blocks_the_rest() -> None:
    stream, events = _stream()
    stream.feed("Ponds must ")
    stream.feed("<")
    stream.feed('functions.search>{"query": "detention"}</functions.search>')
    stream.feed("leaked answer")

    assert _delta_text(events) == "Ponds must "
    assert all("<functions." not in str(event.get("text", "")) for event in events)


def test_withholds_partial_tool_call_marker_character_by_character() -> None:
    stream, events = _stream()
    stream.feed("Checking the library. ")
    for char in "<tool_call":
        stream.feed(char)
    stream.feed(">search</tool_call>should stay hidden")

    assert _delta_text(events) == "Checking the library. "
    assert all("<tool_call" not in str(event.get("text", "")) for event in events)


def test_blocks_uppercase_functions_marker() -> None:
    stream, events = _stream()
    stream.feed('Hi <FUNCTIONS.search>{"query": "x"}</FUNCTIONS.search>')

    assert _delta_text(events) == "Hi "


def test_emits_angle_bracket_that_is_not_a_tool_marker() -> None:
    stream, events = _stream()
    stream.feed("See ")
    stream.feed("<")
    stream.feed("p>Table 2-2</p>")

    assert _delta_text(events) == "See <p>Table 2-2</p>"


def test_finish_resets_visible_prefix_when_response_has_tool_calls() -> None:
    stream, events = _stream()
    stream.feed('Checking. <functions.search>{"query": "x"}</functions.search>')
    stream.finish(_response("", [ToolCall(id="call-1", name="search", arguments={})]))

    assert events == [
        {"event": "answer_delta", "text": "Checking. "},
        {"event": "answer_reset"},
    ]


def test_finish_keeps_matching_streamed_answer() -> None:
    stream, events = _stream()
    stream.feed("The pond must detain runoff.")
    stream.finish(_response("The pond must detain runoff."))

    assert events == [{"event": "answer_delta", "text": "The pond must detain runoff."}]


def test_finish_replaces_mismatch_with_canonical_content() -> None:
    stream, events = _stream()
    stream.feed("partial")
    stream.finish(_response("full answer"))

    assert events == [
        {"event": "answer_delta", "text": "partial"},
        {"event": "answer_reset"},
        {"event": "answer_delta", "text": "full answer"},
    ]


def test_finish_emits_withheld_prefix_when_stream_ended_without_a_marker() -> None:
    stream, events = _stream()
    stream.feed("See <")
    stream.finish(_response("See <"))

    assert _delta_text(events) == "See <"
    assert all(event.get("event") != "answer_reset" for event in events)


def test_abandon_resets_visible_text_before_retry() -> None:
    stream, events = _stream()
    stream.feed("first attempt")
    stream.abandon()

    assert events[-1] == {"event": "answer_reset"}


def test_without_writer_does_not_expose_a_feed_callback() -> None:
    stream = AnswerStream(None)
    assert stream.callback is None
    stream.feed("<functions.search>{}</functions.search>")
    stream.finish(_response("ok"))
    stream.abandon()
