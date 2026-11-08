"""Free-tier model gateway with explicit provider allow-list and safe diagnostics.

Provider credentials are read only from process environment variables. They are
never accepted in request bodies, returned by status endpoints, or written to DB.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

PROVIDERS: dict[str, dict[str, str]] = {
    "groq": {
        "label": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
        "default_model": "llama-3.3-70b-versatile",
        "signup_url": "https://console.groq.com/keys",
    },
    "gemini": {
        "label": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "key_env": "GEMINI_API_KEY",
        "default_model": "gemini-2.5-flash",
        "signup_url": "https://aistudio.google.com/apikey",
    },
    "openrouter": {
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "key_env": "OPENROUTER_API_KEY",
        "default_model": "google/gemma-3-27b-it:free",
        "signup_url": "https://openrouter.ai/keys",
    },
}


class ModelGatewayError(RuntimeError):
    """Safe, user-displayable provider error without credentials."""


def provider_status() -> list[dict[str, Any]]:
    result = []
    for key, item in PROVIDERS.items():
        configured = bool(os.getenv(item["key_env"], "").strip())
        result.append({
            "id": key,
            "name": item["label"],
            "configured": configured,
            "status": "ready-to-test" if configured else "key-required",
            "key_env": item["key_env"],
            "default_model": item["default_model"],
            "signup_url": item["signup_url"],
            "free_tier": True,
            "paid_fallback": False,
        })
    return result


def chat_test(provider: str, model: str, prompt: str) -> dict[str, Any]:
    if provider not in PROVIDERS:
        raise ModelGatewayError("Unsupported provider. Choose Groq, Gemini, or OpenRouter.")
    if not model.strip() or len(model) > 160:
        raise ModelGatewayError("Enter a valid model identifier.")
    if not prompt.strip() or len(prompt) > 4000:
        raise ModelGatewayError("Prompt must contain 1–4000 characters.")

    item = PROVIDERS[provider]
    api_key = os.getenv(item["key_env"], "").strip()
    if not api_key:
        raise ModelGatewayError(
            f"{item['label']} is not connected. Set {item['key_env']} in the hosting environment."
        )

    payload = json.dumps({
        "model": model.strip(),
        "messages": [{"role": "user", "content": prompt.strip()}],
        "max_tokens": 256,
        "temperature": 0.2,
    }).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://ai-operating-system.local"
        headers["X-Title"] = "AI Operating System"
    request = urllib.request.Request(
        item["base_url"] + "/chat/completions",
        data=payload,
        headers=headers,
        method="POST",
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=35) as response:
            raw = response.read(1_000_000)
            data = json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # Do not return provider response bodies: they can contain sensitive metadata.
        if exc.code in (401, 403):
            raise ModelGatewayError("Provider rejected the key or account permissions (401/403).") from None
        if exc.code == 429:
            raise ModelGatewayError("Provider free-tier rate limit reached (429). Try later.") from None
        raise ModelGatewayError(f"Provider request failed with HTTP {exc.code}.") from None
    except (urllib.error.URLError, TimeoutError):
        raise ModelGatewayError("Provider is unreachable or timed out. No paid fallback was attempted.") from None
    except (ValueError, KeyError, IndexError, TypeError):
        raise ModelGatewayError("Provider returned an unreadable response.") from None

    try:
        answer = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise ModelGatewayError("Provider response did not contain a chat completion.") from None
    if not isinstance(answer, str) or not answer.strip():
        raise ModelGatewayError("Provider returned an empty response.")
    usage = data.get("usage") or {}
    return {
        "provider": provider,
        "model": model.strip(),
        "status": "success",
        "latency_ms": round((time.monotonic() - started) * 1000),
        "answer": answer[:12000],
        "usage": {
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
        },
        "paid_fallback_used": False,
    }
