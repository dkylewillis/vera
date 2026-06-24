from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol


Message = dict[str, str]


@dataclass(frozen=True)
class LlmConfig:
    provider: str = "none"
    model: str = ""
    base_url: str = ""
    api_key_env: str = ""
    api_key: str = ""
    auth_type: str = "none"
    temperature: float = 0.2
    max_tokens: int = 700
    timeout: float = 60.0

    @classmethod
    def from_request(cls, raw: Any) -> "LlmConfig":
        if not isinstance(raw, dict):
            return cls()
        return cls(
            provider=str(raw.get("provider", "none") or "none"),
            model=str(raw.get("model", "") or ""),
            base_url=str(raw.get("base_url", "") or ""),
            api_key_env=str(raw.get("api_key_env", "") or ""),
            api_key=str(raw.get("api_key", "") or ""),
            auth_type=str(raw.get("auth_type", "none") or "none"),
            temperature=float(raw.get("temperature", 0.2) or 0.2),
            max_tokens=int(raw.get("max_tokens", 700) or 700),
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


class OpenAiCompatibleProvider:
    provider_name = "openai_compatible"

    def chat(
        self,
        messages: list[Message],
        config: LlmConfig,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
    ) -> ChatResponse:
        if not config.model.strip():
            raise ValueError("LLM model is required")
        if not config.base_url.strip():
            raise ValueError("LLM base URL is required")

        url = _chat_completions_url(config.base_url)
        headers = _auth_headers(config)

        def build_payload(token_param: str, include_temperature: bool) -> dict[str, Any]:
            payload: dict[str, Any] = {
                "model": config.model,
                "messages": messages,
                token_param: config.max_tokens,
                "stream": False,
            }
            if include_temperature:
                payload["temperature"] = config.temperature
            if tools:
                payload["tools"] = tools
                payload["tool_choice"] = tool_choice
            return payload

        def post(token_param: str, include_temperature: bool) -> dict[str, Any]:
            body = json.dumps(build_payload(token_param, include_temperature)).encode("utf-8")
            request = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(request, timeout=config.timeout) as response:
                return json.loads(response.read().decode("utf-8"))

        token_param = "max_tokens"
        include_temperature = True
        response_payload: dict[str, Any] | None = None
        # Newer OpenAI models reject max_tokens and/or non-default temperature; retry by
        # adapting the payload based on the provider's "unsupported_parameter" feedback.
        for _ in range(3):
            try:
                response_payload = post(token_param, include_temperature)
                break
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                if exc.code == 400 and token_param == "max_tokens" and "max_completion_tokens" in detail:
                    token_param = "max_completion_tokens"
                    continue
                if exc.code == 400 and include_temperature and "'temperature'" in detail:
                    include_temperature = False
                    continue
                if exc.code in (400, 404, 422) and tools and _tools_rejected(detail):
                    raise ToolsUnsupportedError(detail) from exc
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


_SUPPORTED_PROVIDERS = {"openai", "openai_compatible", "ollama", "lmstudio", "lm_studio"}


def chat(
    messages: list[Message],
    config: LlmConfig,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str = "auto",
) -> ChatResponse:
    provider = config.provider.strip().lower()
    if provider in _SUPPORTED_PROVIDERS:
        return OpenAiCompatibleProvider().chat(messages, config, tools=tools, tool_choice=tool_choice)
    raise ValueError(f"Unsupported LLM provider: {config.provider}")


def generate(messages: list[Message], config: LlmConfig) -> LlmResult:
    provider = config.provider.strip().lower()
    if provider in _SUPPORTED_PROVIDERS:
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