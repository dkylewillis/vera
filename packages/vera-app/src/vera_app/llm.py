from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Protocol


# `content` is usually a plain string, but may be a list of OpenAI-style content
# parts (e.g. `{"type": "text", ...}` / `{"type": "image_url", ...}`) for
# multimodal messages carrying figure images.
Message = dict[str, Any]


@dataclass(frozen=True)
class LlmConfig:
    provider: str = "none"
    provider_key: str = ""
    model: str = ""
    base_url: str = ""
    api_key_env: str = ""
    api_key: str = ""
    auth_type: str = "none"
    temperature: float = 0.2
    reasoning_effort: str = ""
    service_tier: str = ""
    timeout: float = 60.0

    @classmethod
    def from_request(cls, raw: Any) -> "LlmConfig":
        if not isinstance(raw, dict):
            return cls()
        return cls(
            provider=str(raw.get("provider", "none") or "none"),
            provider_key=str(raw.get("provider_key", "") or ""),
            model=str(raw.get("model", "") or ""),
            base_url=str(raw.get("base_url", "") or ""),
            api_key_env=str(raw.get("api_key_env", "") or ""),
            api_key=str(raw.get("api_key", "") or ""),
            auth_type=str(raw.get("auth_type", "none") or "none"),
            temperature=float(raw.get("temperature", 0.2) or 0.2),
            reasoning_effort=str(raw.get("reasoning_effort", "") or ""),
            service_tier=str(raw.get("service_tier", "") or ""),
            timeout=float(raw.get("timeout", 60.0) or 60.0),
        )

    @property
    def enabled(self) -> bool:
        return self.provider.strip().lower() not in {"", "none", "off", "disabled"}


@dataclass(frozen=True)
class LlmResult:
    answer: str
    provider: str
    model: str
    usage: dict[str, Any] | None = None


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ChatResponse:
    content: str
    tool_calls: list[ToolCall]
    message: dict[str, Any]
    model: str
    usage: dict[str, Any] | None = None


class ToolsUnsupportedError(RuntimeError):
    """Raised when a provider rejects tool/function-calling requests."""


class VisionUnsupportedError(RuntimeError):
    """Raised when a provider rejects image content in a message."""


class LlmProvider(Protocol):
    def generate(self, messages: list[Message], config: LlmConfig) -> LlmResult: ...


def _chat_completions_url(base_url: str) -> str:
    url = f"{base_url.rstrip('/')}/chat/completions"
    if not url.endswith("/v1/chat/completions") and "/v1/" not in url:
        url = f"{base_url.rstrip('/')}/v1/chat/completions"
    return url


def _auth_headers(config: LlmConfig) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if config.auth_type == "oauth":
        raise ValueError("OAuth LLM auth is not implemented yet; use a saved API key or environment variable.")
    api_key = config.api_key or (os.environ.get(config.api_key_env) if config.api_key_env else None)
    if config.auth_type == "api_key" and not api_key:
        raise ValueError("LLM API key is required for API key auth")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _tools_rejected(detail: str) -> bool:
    lowered = detail.lower()
    if "max_completion_tokens" in lowered or "'temperature'" in lowered:
        return False
    return any(token in lowered for token in ("tool", "function call", "function_call", "functions"))


def _model_options_rejected(detail: str) -> bool:
    lowered = detail.lower()
    return any(
        token in lowered
        for token in ("reasoning", "service_tier", "service tier", "verbosity")
    )


def _has_image_content(messages: list[Message]) -> bool:
    """True if any message carries an `image_url` content part."""
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and part.get("type") == "image_url":
                return True
    return False


def _vision_rejected(detail: str) -> bool:
    lowered = detail.lower()
    return any(
        token in lowered
        for token in ("image", "vision", "multimodal", "image_url", "unsupported content", "invalid content")
    )


# Some models (and some local servers) don't emit native `tool_calls` and instead
# write the call inline as text, e.g.  <functions.search>{"query": "..."}</functions.search>.
# Capture well-formed blocks so we can run them, and strip any malformed leftovers
# (e.g. `<functions.search />` or `<functions.search / LATER?`) so the raw markup
# never leaks into the visible answer.
_TEXT_TOOL_CALL_RE = re.compile(
    r"<functions\.(?P<name>[A-Za-z0-9_]+)\s*>(?P<args>.*?)</functions\.(?P=name)\s*>",
    re.DOTALL,
)
_TEXT_TOOL_LEFTOVER_RE = re.compile(r"</?functions\.[A-Za-z0-9_]+\b[^>\n]*/?>?")


def _extract_text_tool_calls(content: str) -> tuple[str, list["ToolCall"]]:
    """Pull inline `<functions.NAME>{json}</functions.NAME>` calls out of text content.

    Returns the cleaned content (with the markup removed) and any parsed tool calls.
    """
    if "functions." not in content:
        return content, []
    calls: list[ToolCall] = []
    for index, match in enumerate(_TEXT_TOOL_CALL_RE.finditer(content)):
        name = match.group("name")
        raw_args = (match.group("args") or "").strip()
        try:
            arguments = json.loads(raw_args) if raw_args else {}
        except json.JSONDecodeError:
            arguments = {}
        if not isinstance(arguments, dict):
            arguments = {}
        calls.append(ToolCall(id=f"text_call_{index}", name=name, arguments=arguments))
    cleaned = _TEXT_TOOL_CALL_RE.sub("", content)
    cleaned = _TEXT_TOOL_LEFTOVER_RE.sub("", cleaned).strip()
    return cleaned, calls


def _consume_stream(response: Any, on_delta: Callable[[str], None]) -> dict[str, Any]:
    """Read an OpenAI-compatible SSE stream into a non-streamed response payload.

    Accumulates content and tool-call deltas so the caller can reuse the same
    parsing path as a regular (non-streamed) completion. ``on_delta`` is invoked
    with each text fragment as it arrives.
    """
    content_parts: list[str] = []
    tool_calls_acc: dict[int, dict[str, Any]] = {}
    model_name = ""
    usage: dict[str, Any] | None = None
    for raw_line in response:
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line or not line.startswith("data:"):
            continue
        data = line[len("data:"):].strip()
        if data == "[DONE]":
            break
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            continue
        if chunk.get("model"):
            model_name = str(chunk["model"])
        if chunk.get("usage"):
            usage = chunk["usage"]
        choices = chunk.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta") or {}
        piece = delta.get("content")
        if piece:
            content_parts.append(piece)
            on_delta(piece)
        for raw_call in delta.get("tool_calls") or []:
            if not isinstance(raw_call, dict):
                continue
            index = int(raw_call.get("index", 0) or 0)
            slot = tool_calls_acc.setdefault(index, {"id": None, "name": "", "arguments": ""})
            if raw_call.get("id"):
                slot["id"] = raw_call["id"]
            function = raw_call.get("function") or {}
            if function.get("name"):
                slot["name"] = function["name"]
            if function.get("arguments"):
                slot["arguments"] += function["arguments"]

    message: dict[str, Any] = {"role": "assistant", "content": "".join(content_parts)}
    if tool_calls_acc:
        message["tool_calls"] = [
            {
                "id": slot["id"] or slot["name"] or f"call_{index}",
                "type": "function",
                "function": {"name": slot["name"], "arguments": slot["arguments"]},
            }
            for index, slot in sorted(tool_calls_acc.items())
        ]
    return {"choices": [{"message": message}], "model": model_name, "usage": usage}


def _responses_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/responses"):
        return base
    if base.endswith("/v1") or "/v1/" in base:
        return f"{base}/responses"
    return f"{base}/v1/responses"


def _response_input_content(content: Any) -> Any:
    if not isinstance(content, list):
        return content if content is not None else ""
    parts: list[dict[str, Any]] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        if part.get("type") == "text":
            parts.append({"type": "input_text", "text": str(part.get("text") or "")})
        elif part.get("type") == "image_url":
            image_url = part.get("image_url") or {}
            url = image_url.get("url") if isinstance(image_url, dict) else None
            if url:
                parts.append({"type": "input_image", "image_url": str(url)})
    return parts


def _messages_to_response_input(messages: list[Message]) -> list[dict[str, Any]]:
    """Translate VERA's Chat Completions transcript to Responses API Items."""
    items: list[dict[str, Any]] = []
    for message in messages:
        replay_items = message.get("_responses_items")
        if isinstance(replay_items, list):
            items.extend(item for item in replay_items if isinstance(item, dict))
            continue
        role = str(message.get("role") or "")
        if role == "tool":
            items.append({
                "type": "function_call_output",
                "call_id": str(message.get("tool_call_id") or ""),
                "output": str(message.get("content") or ""),
            })
            continue
        content = message.get("content")
        if content not in (None, "", []):
            items.append({"role": role, "content": _response_input_content(content)})
        if role == "assistant":
            for raw_call in message.get("tool_calls") or []:
                if not isinstance(raw_call, dict):
                    continue
                function = raw_call.get("function") or {}
                items.append({
                    "type": "function_call",
                    "call_id": str(raw_call.get("id") or function.get("name") or ""),
                    "name": str(function.get("name") or ""),
                    "arguments": str(function.get("arguments") or "{}"),
                })
    return items


def _responses_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for tool in tools or []:
        if tool.get("type") != "function" or not isinstance(tool.get("function"), dict):
            continue
        function = tool["function"]
        converted.append({
            "type": "function",
            "name": str(function.get("name") or ""),
            "description": str(function.get("description") or ""),
            "parameters": function.get("parameters") or {"type": "object", "properties": {}},
            "strict": bool(function.get("strict", False)),
        })
    return converted


def _consume_responses_stream(response: Any, on_delta: Callable[[str], None]) -> dict[str, Any]:
    final_response: dict[str, Any] | None = None
    output_items: dict[int, dict[str, Any]] = {}
    response_id = ""
    model = ""
    usage: dict[str, Any] | None = None
    for raw_line in response:
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line or not line.startswith("data:"):
            continue
        data = line[len("data:"):].strip()
        if data == "[DONE]":
            break
        try:
            event = json.loads(data)
        except json.JSONDecodeError:
            continue
        event_type = event.get("type")
        if event_type == "response.output_text.delta":
            piece = str(event.get("delta") or "")
            if piece:
                on_delta(piece)
        elif event_type in {"response.output_item.added", "response.output_item.done"}:
            item = event.get("item")
            if isinstance(item, dict):
                output_items[int(event.get("output_index", len(output_items)) or 0)] = item
        elif event_type == "response.function_call_arguments.delta":
            index = int(event.get("output_index", 0) or 0)
            item = output_items.setdefault(index, {
                "type": "function_call",
                "id": event.get("item_id"),
                "call_id": event.get("item_id"),
                "name": "",
                "arguments": "",
            })
            item["arguments"] = str(item.get("arguments") or "") + str(event.get("delta") or "")
        elif event_type == "response.function_call_arguments.done":
            index = int(event.get("output_index", 0) or 0)
            item = event.get("item")
            if isinstance(item, dict):
                output_items[index] = item
            elif index in output_items:
                output_items[index]["arguments"] = str(event.get("arguments") or output_items[index].get("arguments") or "")
                output_items[index]["name"] = str(event.get("name") or output_items[index].get("name") or "")
        elif event_type == "response.completed":
            completed = event.get("response")
            if isinstance(completed, dict):
                final_response = completed
        elif event_type in {"response.failed", "error"}:
            detail = event.get("error") or event
            raise RuntimeError(f"OpenAI Responses API stream failed: {detail}")
        response_payload = event.get("response")
        if isinstance(response_payload, dict):
            response_id = str(response_payload.get("id") or response_id)
            model = str(response_payload.get("model") or model)
            if isinstance(response_payload.get("usage"), dict):
                usage = response_payload["usage"]
    if final_response is not None:
        return final_response
    return {
        "id": response_id,
        "model": model,
        "output": [item for _, item in sorted(output_items.items())],
        "usage": usage,
    }


def _chat_response_from_responses(payload: dict[str, Any], fallback_model: str) -> ChatResponse:
    output = payload.get("output") or []
    content_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    chat_tool_calls: list[dict[str, Any]] = []
    replay_items: list[dict[str, Any]] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        replay_items.append(item)
        if item.get("type") == "message":
            for part in item.get("content") or []:
                if isinstance(part, dict) and part.get("type") == "output_text" and part.get("text"):
                    content_parts.append(str(part["text"]))
        elif item.get("type") == "function_call":
            call_id = str(item.get("call_id") or item.get("id") or item.get("name") or "")
            name = str(item.get("name") or "")
            raw_arguments = str(item.get("arguments") or "{}")
            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError:
                arguments = {}
            if not isinstance(arguments, dict):
                arguments = {}
            tool_calls.append(ToolCall(id=call_id, name=name, arguments=arguments))
            chat_tool_calls.append({
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": raw_arguments},
            })
    content = "".join(content_parts).strip()
    message: dict[str, Any] = {
        "role": "assistant",
        "content": content,
        "_responses_items": replay_items,
    }
    if chat_tool_calls:
        message["tool_calls"] = chat_tool_calls
    return ChatResponse(
        content=content,
        tool_calls=tool_calls,
        message=message,
        model=str(payload.get("model") or fallback_model),
        usage=payload.get("usage") if isinstance(payload.get("usage"), dict) else None,
    )


class OpenAiCompatibleProvider:
    provider_name = "openai_compatible"

    def chat(
        self,
        messages: list[Message],
        config: LlmConfig,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
        on_delta: Callable[[str], None] | None = None,
    ) -> ChatResponse:
        if not config.model.strip():
            raise ValueError("LLM model is required")
        if not config.base_url.strip():
            raise ValueError("LLM base URL is required")

        url = _chat_completions_url(config.base_url)
        headers = _auth_headers(config)
        stream = on_delta is not None

        def build_payload(include_temperature: bool, include_options: bool) -> dict[str, Any]:
            payload: dict[str, Any] = {
                "model": config.model,
                "messages": messages,
                "stream": stream,
            }
            if include_temperature:
                payload["temperature"] = config.temperature
            if include_options:
                effort = config.reasoning_effort.strip().lower()
                if effort:
                    is_openrouter = config.provider_key == "openrouter" or "openrouter.ai" in config.base_url.lower()
                    model_name = config.model.lower()
                    is_adaptive_anthropic = is_openrouter and model_name.startswith("anthropic/") and any(
                        token in model_name for token in ("fable", "mythos", "opus-4.6", "opus-4.7", "opus-4.8")
                    )
                    if is_adaptive_anthropic:
                        if effort != "none":
                            payload["verbosity"] = effort
                    elif is_openrouter:
                        payload["reasoning"] = {"enabled": False} if effort == "none" else {"effort": effort}
                    else:
                        payload["reasoning_effort"] = effort
                if config.service_tier.strip():
                    payload["service_tier"] = config.service_tier.strip()
            if tools:
                payload["tools"] = tools
                payload["tool_choice"] = tool_choice
            return payload

        def post(include_temperature: bool, include_options: bool) -> dict[str, Any]:
            body = json.dumps(build_payload(include_temperature, include_options)).encode("utf-8")
            request = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(request, timeout=config.timeout) as response:
                if stream:
                    return _consume_stream(response, on_delta)
                return json.loads(response.read().decode("utf-8"))

        include_temperature = True
        include_options = bool(config.reasoning_effort.strip() or config.service_tier.strip())
        response_payload: dict[str, Any] | None = None
        # Newer OpenAI models reject a non-default temperature; retry by adapting the
        # payload based on the provider's "unsupported_parameter" feedback.
        # HTTP errors are raised before any streamed body is read, so a retry cannot
        # double-emit deltas.
        for _ in range(4):
            try:
                response_payload = post(include_temperature, include_options)
                break
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                if exc.code == 400 and include_temperature and "'temperature'" in detail:
                    include_temperature = False
                    continue
                if exc.code in (400, 422) and include_options and _model_options_rejected(detail):
                    include_options = False
                    continue
                if exc.code in (400, 404, 422) and tools and _tools_rejected(detail):
                    raise ToolsUnsupportedError(detail) from exc
                if exc.code in (400, 415, 422) and _has_image_content(messages) and _vision_rejected(detail):
                    raise VisionUnsupportedError(detail) from exc
                raise RuntimeError(f"LLM provider returned HTTP {exc.code}: {detail}") from exc
            except urllib.error.URLError as exc:
                raise RuntimeError(f"Unable to reach LLM provider: {exc.reason}") from exc
        if response_payload is None:
            raise RuntimeError("LLM provider rejected the request after adjusting unsupported parameters.")

        choices = response_payload.get("choices") or []
        message = choices[0].get("message", {}) if choices else {}
        if not isinstance(message, dict):
            message = {}
        content = str(message.get("content") or "").strip()
        tool_calls: list[ToolCall] = []
        for raw_call in message.get("tool_calls") or []:
            if not isinstance(raw_call, dict):
                continue
            function = raw_call.get("function") or {}
            name = str(function.get("name") or "")
            if not name:
                continue
            raw_args = function.get("arguments")
            if isinstance(raw_args, str):
                try:
                    arguments = json.loads(raw_args) if raw_args.strip() else {}
                except json.JSONDecodeError:
                    arguments = {}
            elif isinstance(raw_args, dict):
                arguments = raw_args
            else:
                arguments = {}
            tool_calls.append(ToolCall(id=str(raw_call.get("id") or name), name=name, arguments=arguments))

        # Fallback: some models emit tool calls as inline text instead of using the
        # structured `tool_calls` field. Parse those out so the agent loop can run
        # them and the raw markup never reaches the user.
        if not tool_calls and content:
            cleaned, text_calls = _extract_text_tool_calls(content)
            if text_calls:
                content = cleaned
                tool_calls = text_calls
                # Rebuild a well-formed assistant message so the follow-up `tool`
                # messages have matching `tool_calls` (required by strict providers).
                message = {
                    "role": "assistant",
                    "content": cleaned,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": json.dumps(call.arguments),
                            },
                        }
                        for call in text_calls
                    ],
                }

        return ChatResponse(
            content=content,
            tool_calls=tool_calls,
            message=message,
            model=str(response_payload.get("model") or config.model),
            usage=response_payload.get("usage"),
        )

    def generate(self, messages: list[Message], config: LlmConfig) -> LlmResult:
        response = self.chat(messages, config)
        if not response.content:
            raise RuntimeError("LLM provider returned no message content")
        return LlmResult(
            answer=response.content,
            provider=self.provider_name,
            model=response.model,
            usage=response.usage,
        )


class OpenAiResponsesProvider:
    """OpenAI Responses API adapter for reasoning models with tool calling."""

    provider_name = "openai"

    def chat(
        self,
        messages: list[Message],
        config: LlmConfig,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
        on_delta: Callable[[str], None] | None = None,
    ) -> ChatResponse:
        if not config.model.strip():
            raise ValueError("LLM model is required")
        if not config.base_url.strip():
            raise ValueError("LLM base URL is required")

        url = _responses_url(config.base_url)
        headers = _auth_headers(config)
        stream = on_delta is not None
        responses_tools = _responses_tools(tools)
        include_reasoning = bool(config.reasoning_effort.strip())
        include_service_tier = bool(config.service_tier.strip())
        response_payload: dict[str, Any] | None = None

        def build_payload() -> dict[str, Any]:
            payload: dict[str, Any] = {
                "model": config.model,
                "input": _messages_to_response_input(messages),
                "store": False,
                "include": ["reasoning.encrypted_content"],
                "stream": stream,
            }
            if include_reasoning:
                payload["reasoning"] = {"effort": config.reasoning_effort.strip().lower()}
            if include_service_tier:
                payload["service_tier"] = config.service_tier.strip()
            if responses_tools:
                payload["tools"] = responses_tools
                payload["tool_choice"] = tool_choice
            return payload

        for _ in range(3):
            try:
                request = urllib.request.Request(
                    url,
                    data=json.dumps(build_payload()).encode("utf-8"),
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=config.timeout) as response:
                    if stream:
                        response_payload = _consume_responses_stream(response, on_delta)
                    else:
                        response_payload = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                lowered = detail.lower()
                if exc.code in (400, 422) and include_service_tier and (
                    "service_tier" in lowered or "service tier" in lowered
                ):
                    include_service_tier = False
                    continue
                if exc.code in (400, 422) and include_reasoning and "reasoning" in lowered:
                    include_reasoning = False
                    continue
                if exc.code in (400, 404, 422) and responses_tools and _tools_rejected(detail):
                    raise ToolsUnsupportedError(detail) from exc
                if exc.code in (400, 415, 422) and _has_image_content(messages) and _vision_rejected(detail):
                    raise VisionUnsupportedError(detail) from exc
                raise RuntimeError(f"OpenAI Responses API returned HTTP {exc.code}: {detail}") from exc
            except urllib.error.URLError as exc:
                raise RuntimeError(f"Unable to reach OpenAI Responses API: {exc.reason}") from exc
        if response_payload is None:
            raise RuntimeError("OpenAI Responses API rejected the request after adjusting unsupported parameters.")
        return _chat_response_from_responses(response_payload, config.model)

    def generate(self, messages: list[Message], config: LlmConfig) -> LlmResult:
        response = self.chat(messages, config)
        if not response.content:
            raise RuntimeError("LLM provider returned no message content")
        return LlmResult(
            answer=response.content,
            provider=self.provider_name,
            model=response.model,
            usage=response.usage,
        )


_SUPPORTED_PROVIDERS = {"openai", "openai_compatible", "ollama", "lmstudio", "lm_studio"}


def _uses_openai_responses(config: LlmConfig) -> bool:
    model = config.model.strip().lower()
    is_first_party_openai = config.provider_key == "openai" or "api.openai.com" in config.base_url.lower()
    return is_first_party_openai and (model.startswith("gpt-5.6") or model == "gpt-5.6")


def chat(
    messages: list[Message],
    config: LlmConfig,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str = "auto",
    on_delta: Callable[[str], None] | None = None,
) -> ChatResponse:
    provider = config.provider.strip().lower()
    if provider in _SUPPORTED_PROVIDERS:
        if _uses_openai_responses(config):
            return OpenAiResponsesProvider().chat(messages, config, tools=tools, tool_choice=tool_choice, on_delta=on_delta)
        return OpenAiCompatibleProvider().chat(messages, config, tools=tools, tool_choice=tool_choice, on_delta=on_delta)
    raise ValueError(f"Unsupported LLM provider: {config.provider}")


def generate(messages: list[Message], config: LlmConfig) -> LlmResult:
    provider = config.provider.strip().lower()
    if provider in _SUPPORTED_PROVIDERS:
        if _uses_openai_responses(config):
            return OpenAiResponsesProvider().generate(messages, config)
        return OpenAiCompatibleProvider().generate(messages, config)
    raise ValueError(f"Unsupported LLM provider: {config.provider}")


def _models_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/models"):
        return base
    if base.endswith("/v1") or "/v1/" in base:
        return f"{base}/models"
    return f"{base}/v1/models"


def list_models(config: LlmConfig) -> list[str]:
    """Query an OpenAI-compatible provider for its available model ids."""
    if not config.base_url.strip():
        raise ValueError("LLM base URL is required")
    if config.auth_type == "oauth":
        raise ValueError("OAuth LLM auth is not implemented yet; use a saved API key or environment variable.")

    url = _models_url(config.base_url)
    headers = {"Accept": "application/json"}
    api_key = config.api_key or (os.environ.get(config.api_key_env) if config.api_key_env else None)
    if config.auth_type == "api_key" and not api_key:
        raise ValueError("LLM API key is required for API key auth")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=config.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM provider returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Unable to reach LLM provider: {exc.reason}") from exc

    entries = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        # Ollama's native /api/tags shape: {"models": [{"name": ...}]}
        entries = payload.get("models") if isinstance(payload, dict) else None
    models: list[str] = []
    for entry in entries or []:
        if isinstance(entry, dict):
            model_id = entry.get("id") or entry.get("name") or entry.get("model")
            if model_id:
                models.append(str(model_id))
        elif isinstance(entry, str):
            models.append(entry)
    return sorted(dict.fromkeys(models))