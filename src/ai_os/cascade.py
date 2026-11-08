"""Free-first multi-provider LLM routing adapted from the selected MIT project.

Only providers explicitly configured in AI_OS_LLM_PROVIDERS are eligible.
Paid/uncertain providers remain blocked unless AI_OS_ALLOW_PAID_LLM=true.
"""
from __future__ import annotations

import os
import time
from typing import Any

import httpx

from ai_os.llm import load_providers


# Process-local circuit breaker. Durable quota accounting is a later phase.
_failures: dict[str, tuple[int, float]] = {}
_COOLDOWN_SECONDS = 60.0


class AllProvidersFailed(RuntimeError):
    def __init__(self, failures: list[dict[str, str]]):
        self.failures = failures
        super().__init__("All eligible configured LLM providers failed")


def provider_order() -> list[Any]:
    allow_paid = os.getenv("AI_OS_ALLOW_PAID_LLM", "false").lower() == "true"
    providers = [
        p for p in load_providers()
        if p.api_key_configured and (p.free_tier_confirmed or allow_paid)
    ]
    now = time.monotonic()
    available = []
    cooling = []
    for p in providers:
        count, last_failure = _failures.get(p.name, (0, 0.0))
        if count >= 3 and now - last_failure < _COOLDOWN_SECONDS:
            cooling.append(p)
        else:
            available.append(p)
    return available or cooling


async def cascade_chat(
    prompt: str,
    *,
    system: str | None = None,
    max_tokens: int = 500,
    temperature: float = 0.2,
) -> dict[str, Any]:
    providers = provider_order()
    if not providers:
        raise LookupError("No eligible configured providers with API keys are available")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    failures: list[dict[str, str]] = []

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
        for provider in providers:
            key = os.getenv(provider.api_key_env, "").strip() if provider.api_key_env else ""
            url = f"{provider.base_url}/chat/completions"
            payload = {
                "model": provider.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            try:
                headers = {"Content-Type": "application/json"}
                if provider.auth_style != "none":
                    headers["Authorization"] = f"Bearer {key}"
                response = await client.post(url, headers=headers, json=payload)
                if response.status_code >= 400:
                    # Do not expose provider response bodies; they can contain sensitive data.
                    failures.append({"provider": provider.name, "error": f"HTTP {response.status_code}"})
                    _record_failure(provider.name)
                    continue
                data = response.json()
                choices = data.get("choices") or []
                content = choices[0].get("message", {}).get("content") if choices else None
                if not isinstance(content, str) or not content.strip():
                    failures.append({"provider": provider.name, "error": "Invalid completion response"})
                    _record_failure(provider.name)
                    continue
                _failures.pop(provider.name, None)
                usage = data.get("usage") or {}
                return {
                    "status": "ok",
                    "provider": provider.name,
                    "model": provider.model,
                    "response": content,
                    "usage": {
                        "prompt_tokens": usage.get("prompt_tokens"),
                        "completion_tokens": usage.get("completion_tokens"),
                        "total_tokens": usage.get("total_tokens"),
                    },
                    "fallback_count": len(failures),
                }
            except (httpx.TimeoutException, httpx.NetworkError, ValueError):
                failures.append({"provider": provider.name, "error": "Timeout, network, or invalid JSON response"})
                _record_failure(provider.name)
    raise AllProvidersFailed(failures)


def _record_failure(name: str) -> None:
    count, _ = _failures.get(name, (0, 0.0))
    _failures[name] = (count + 1, time.monotonic())
