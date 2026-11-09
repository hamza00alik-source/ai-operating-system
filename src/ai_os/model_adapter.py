"""Provider-neutral OpenAI-compatible chat completion adapter.

No provider is contacted unless AI_OS_MODEL_ENABLED=true and a worker is run.
Credentials are read only from the process environment.
"""
from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def get_model_status() -> dict:
    enabled = os.getenv("AI_OS_MODEL_ENABLED", "false").strip().lower() in {"1", "true", "yes"}
    return {
        "enabled": enabled,
        "provider": os.getenv("AI_OS_MODEL_PROVIDER", "openai-compatible"),
        "model": os.getenv("AI_OS_MODEL_NAME", ""),
        "configured": bool(os.getenv("AI_OS_MODEL_BASE_URL") and os.getenv("AI_OS_MODEL_NAME")),
    }


def _chat_completion(payload: dict, *, timeout: int) -> dict:
    status = get_model_status()
    if not status["enabled"]:
        raise RuntimeError("Model execution is disabled. Set AI_OS_MODEL_ENABLED=true explicitly.")
    base_url = os.getenv("AI_OS_MODEL_BASE_URL", "").rstrip("/")
    model = os.getenv("AI_OS_MODEL_NAME", "")
    api_key = os.getenv("AI_OS_MODEL_API_KEY", "")
    if not base_url or not model:
        raise RuntimeError("Set AI_OS_MODEL_BASE_URL and AI_OS_MODEL_NAME before enabling model execution.")
    body = {"model": model, **payload}
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = Request(f"{base_url}/chat/completions", data=json.dumps(body).encode("utf-8"),
                      headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"Model provider request failed: {type(exc).__name__}") from exc
    if not isinstance(result, dict):
        raise RuntimeError("Model provider returned an unexpected response format.")
    return result


def _message_from_response(body: dict) -> dict:
    try:
        message = body["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Model provider returned an unexpected response format.") from exc
    if not isinstance(message, dict):
        raise RuntimeError("Model provider returned an invalid message.")
    return message


def generate_text(prompt: str, *, timeout: int = 45) -> str:
    body = _chat_completion({
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }, timeout=timeout)
    content = _message_from_response(body).get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Model provider returned empty content.")
    return content.strip()


def generate_agent_turn(prompt: str, tools: list[dict], *, timeout: int = 60) -> dict:
    """Ask an OpenAI-compatible model for either a final response or structured tool calls.

    Tool calls are proposals only. This function never executes a tool and never
    bypasses the owner approval gateway. The caller must validate each proposal
    against the currently discovered MCP catalog and bind it to the active task.
    """
    if not isinstance(tools, list) or not tools:
        return {"kind": "final", "content": generate_text(prompt, timeout=timeout)}
    normalized = []
    for item in tools:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise ValueError("Tool catalog entries must contain a name.")
        name = item["name"]
        if not name or len(name) > 120:
            raise ValueError("Tool catalog contains an invalid tool name.")
        normalized.append({
            "type": "function",
            "function": {
                "name": name,
                "description": str(item.get("description", ""))[:1000],
                "parameters": item.get("input_schema") or {"type": "object", "properties": {}},
            },
        })
    body = _chat_completion({
        "messages": [{"role": "user", "content": prompt}],
        "tools": normalized,
        "tool_choice": "auto",
        "parallel_tool_calls": False,
        "temperature": 0.2,
    }, timeout=timeout)
    message = _message_from_response(body)
    calls = message.get("tool_calls") or []
    if calls:
        if not isinstance(calls, list) or len(calls) != 1:
            raise RuntimeError("Agent must request exactly one MCP tool per turn.")
        call = calls[0]
        try:
            function = call["function"]
            name = function["name"]
            arguments = json.loads(function.get("arguments", "{}"))
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Model returned a malformed tool call.") from exc
        if not isinstance(name, str) or not name or not isinstance(arguments, dict):
            raise RuntimeError("Model tool call must contain a tool name and JSON object arguments.")
        return {"kind": "tool_call", "tool_name": name, "arguments": arguments,
                "call_id": str(call.get("id", ""))[:200]}
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Model returned neither a tool call nor final content.")
    return {"kind": "final", "content": content.strip()}
