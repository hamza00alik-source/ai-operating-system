"""Provider-neutral OpenAI-compatible chat completion adapter.

No provider is contacted unless AI_OS_MODEL_ENABLED=true and the worker is run.
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


def generate_text(prompt: str, *, timeout: int = 45) -> str:
    status = get_model_status()
    if not status["enabled"]:
        raise RuntimeError("Model execution is disabled. Set AI_OS_MODEL_ENABLED=true explicitly.")
    base_url = os.getenv("AI_OS_MODEL_BASE_URL", "").rstrip("/")
    model = os.getenv("AI_OS_MODEL_NAME", "")
    api_key = os.getenv("AI_OS_MODEL_API_KEY", "")
    if not base_url or not model:
        raise RuntimeError("Set AI_OS_MODEL_BASE_URL and AI_OS_MODEL_NAME before enabling model execution.")
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = Request(f"{base_url}/chat/completions", data=payload, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"Model provider request failed: {type(exc).__name__}") from exc
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Model provider returned an unexpected response format.") from exc
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Model provider returned empty content.")
    return content.strip()
