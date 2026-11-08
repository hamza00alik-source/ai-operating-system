"""Provider-neutral OpenAI-compatible LLM adapter.

Providers are configured explicitly through AI_OS_LLM_PROVIDERS. Secrets are
read from named environment variables and are never returned by the API.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    model: str
    api_key_env: str
    free_tier_confirmed: bool = False

    @property
    def api_key_configured(self) -> bool:
        return bool(os.getenv(self.api_key_env, "").strip())


def load_providers() -> list[Provider]:
    raw = os.getenv("AI_OS_LLM_PROVIDERS", "[]")
    try:
        entries = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("AI_OS_LLM_PROVIDERS must be valid JSON") from exc
    if not isinstance(entries, list):
        raise ValueError("AI_OS_LLM_PROVIDERS must be a JSON array")

    providers: list[Provider] = []
    names: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Each LLM provider must be a JSON object")
        name = str(entry.get("name", "")).strip().lower()
        base_url = str(entry.get("base_url", "")).strip().rstrip("/")
        model = str(entry.get("model", "")).strip()
        api_key_env = str(entry.get("api_key_env", "")).strip()
        if not all((name, base_url, model, api_key_env)):
            raise ValueError("Each provider needs name, base_url, model, and api_key_env")
        if name in names:
            raise ValueError(f"Duplicate LLM provider name: {name}")
        if not base_url.startswith("https://"):
            raise ValueError("LLM provider base_url must use HTTPS")
        names.add(name)
        providers.append(Provider(
            name=name,
            base_url=base_url,
            model=model,
            api_key_env=api_key_env,
            free_tier_confirmed=entry.get("free_tier_confirmed") is True,
        ))
    return providers


def provider_status() -> list[dict[str, Any]]:
    allow_paid = os.getenv("AI_OS_ALLOW_PAID_LLM", "false").lower() == "true"
    return [
        {
            "name": p.name,
            "model": p.model,
            "configured": p.api_key_configured,
            "eligible_for_test": p.api_key_configured and (p.free_tier_confirmed or allow_paid),
            "free_tier_confirmed_by_owner": p.free_tier_confirmed,
        }
        for p in load_providers()
    ]


async def test_provider(name: str, prompt: str) -> dict[str, Any]:
    providers = {p.name: p for p in load_providers()}
    provider = providers.get(name.strip().lower())
    if provider is None:
        raise LookupError("Configured LLM provider not found")
    api_key = os.getenv(provider.api_key_env, "").strip()
    if not api_key:
        raise RuntimeError(f"Missing API key environment variable: {provider.api_key_env}")

    allow_paid = os.getenv("AI_OS_ALLOW_PAID_LLM", "false").lower() == "true"
    if not provider.free_tier_confirmed and not allow_paid:
        raise PermissionError(
            "Provider is not marked as free-tier-confirmed. Verify its current pricing "
            "and set free_tier_confirmed=true, or obtain owner approval to enable paid APIs."
        )

    url = f"{provider.base_url}/chat/completions"
    payload = {
        "model": provider.model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 120,
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
    if response.status_code >= 400:
        # Do not expose request headers or secrets in errors.
        detail = response.text[:500]
        raise RuntimeError(f"Provider returned HTTP {response.status_code}: {detail}")
    data = response.json()
    choices = data.get("choices") or []
    content = choices[0].get("message", {}).get("content") if choices else None
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Provider response did not contain a chat completion")
    usage = data.get("usage") or {}
    return {
        "provider": provider.name,
        "model": provider.model,
        "status": "ok",
        "response": content,
        "usage": {
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
        },
    }
