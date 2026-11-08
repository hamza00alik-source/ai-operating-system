"""Provider-neutral, opt-in chat-completions adapter.

No provider is contacted unless AI_OS_MODEL_ENABLED=true. Credentials are read
only from the process environment and are never returned by status responses.
"""
from __future__ import annotations

import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ModelAdapterError(RuntimeError):
    """Safe-to-display model adapter failure."""


def _settings() -> dict:
    return {
        "enabled": os.getenv("AI_OS_MODEL_ENABLED", "false").strip().lower() == "true",
        "provider": os.getenv("AI_OS_MODEL_PROVIDER", "custom").strip() or "custom",
        "model": os.getenv("AI_OS_MODEL_NAME", "").strip(),
        "base_url": os.getenv("AI_OS_MODEL_BASE_URL", "").strip().rstrip("/"),
        "api_key": os.getenv("AI_OS_MODEL_API_KEY", "").strip(),
        "timeout": max(2, min(int(os.getenv("AI_OS_MODEL_TIMEOUT_SECONDS", "30")), 120)),
        "max_tokens": max(1, min(int(os.getenv("AI_OS_MODEL_MAX_TOKENS", "512")), 4096)),
    }


def get_model_status() -> dict:
    """Return safe configuration status; never return the API key or its value."""
    cfg = _settings()
    missing = []
    if not cfg["enabled"]:
        missing.append("AI_OS_MODEL_ENABLED is not true")
    if not cfg["model"]:
        missing.append("AI_OS_MODEL_NAME is not configured")
    if not cfg["base_url"]:
        missing.append("AI_OS_MODEL_BASE_URL is not configured")
    return {
        "enabled": cfg["enabled"],
        "ready": not missing,
        "provider": cfg["provider"],
        "model": cfg["model"] or None,
        "base_url_configured": bool(cfg["base_url"]),
        "authentication": "configured" if cfg["api_key"] else "not_configured",
        "timeout_seconds": cfg["timeout"],
        "max_tokens": cfg["max_tokens"],
        "missing_configuration": missing,
    }


def chat_completion(prompt: str) -> dict:
    """Call an explicitly configured OpenAI-compatible endpoint."""
    cfg = _settings()
    if not cfg["enabled"]:
        raise ModelAdapterError("Model calls are disabled. Set AI_OS_MODEL_ENABLED=true after reviewing provider cost and terms.")
    if not cfg["base_url"] or not cfg["model"]:
        raise ModelAdapterError("Model endpoint and model name must be configured.")
    if not prompt or not prompt.strip():
        raise ModelAdapterError("Prompt must not be empty.")

    base = cfg["base_url"]
    if base.endswith("/chat/completions"):
        endpoint = base
    elif base.endswith("/v1"):
        endpoint = base + "/chat/completions"
    else:
        endpoint = base + "/v1/chat/completions"

    payload = {
        "model": cfg["model"],
        "messages": [{"role": "user", "content": prompt.strip()}],
        "max_tokens": cfg["max_tokens"],
    }
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if cfg["api_key"]:
        headers["Authorization"] = f"Bearer {cfg['api_key']}"
    request = Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    started = time.monotonic()
    try:
        with urlopen(request, timeout=cfg["timeout"]) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        # Do not surface provider response bodies; they can contain sensitive details.
        raise ModelAdapterError(f"Provider returned HTTP {exc.code}. Check provider quota, model ID, and configuration.") from None
    except (URLError, TimeoutError, OSError):
        raise ModelAdapterError("Could not reach the configured model provider. Check the endpoint and network.") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ModelAdapterError("Provider returned an invalid JSON response.") from None

    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise ModelAdapterError("Provider response did not match the OpenAI chat-completions format.") from None
    if not isinstance(text, str) or not text.strip():
        raise ModelAdapterError("Provider returned an empty response.")
    usage = data.get("usage") if isinstance(data, dict) else None
    return {
        "provider": cfg["provider"],
        "model": cfg["model"],
        "response": text,
        "latency_ms": round((time.monotonic() - started) * 1000),
        "usage": usage if isinstance(usage, dict) else None,
    }
