"""Zero-cost guarded LLM gateway.

Only explicitly configured providers marked as free are eligible. Secrets are read
from server environment variables and are never returned by status endpoints.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Provider:
    key: str
    label: str
    base_url_env: str
    model_env: str
    secret_env: str
    free_confirm_env: str
    protocol: str = "openai"


PROVIDERS = (
    Provider("gemini", "Google Gemini", "AI_OS_GEMINI_BASE_URL", "AI_OS_GEMINI_MODEL",
             "AI_OS_GEMINI_API_KEY", "AI_OS_GEMINI_FREE_CONFIRMED", "gemini"),
    Provider("groq", "Groq", "AI_OS_GROQ_BASE_URL", "AI_OS_GROQ_MODEL",
             "AI_OS_GROQ_API_KEY", "AI_OS_GROQ_FREE_CONFIRMED"),
    Provider("mistral", "Mistral", "AI_OS_MISTRAL_BASE_URL", "AI_OS_MISTRAL_MODEL",
             "AI_OS_MISTRAL_API_KEY", "AI_OS_MISTRAL_FREE_CONFIRMED"),
    Provider("cloudflare", "Cloudflare Workers AI", "AI_OS_CLOUDFLARE_BASE_URL",
             "AI_OS_CLOUDFLARE_MODEL", "AI_OS_CLOUDFLARE_API_TOKEN",
             "AI_OS_CLOUDFLARE_FREE_CONFIRMED", "cloudflare"),
    Provider("openai-compatible", "Custom OpenAI-compatible", "AI_OS_CUSTOM_BASE_URL",
             "AI_OS_CUSTOM_MODEL", "AI_OS_CUSTOM_API_KEY",
             "AI_OS_CUSTOM_FREE_CONFIRMED"),
)


def _provider_config(provider: Provider) -> dict[str, Any]:
    base = os.getenv(provider.base_url_env, "").strip().rstrip("/")
    model = os.getenv(provider.model_env, "").strip()
    secret = os.getenv(provider.secret_env, "").strip()
    free = os.getenv(provider.free_confirm_env, "").strip().lower() == "true"
    try:
        from ai_os.credential_vault import PROVIDER_META, get_provider_secret
        if provider.key in PROVIDER_META:
            saved = get_provider_secret(provider.key)
            if saved:
                model, secret, free = saved
                base = PROVIDER_META[provider.key]["base_url"]
    except Exception:
        # Environment-backed configuration remains available during migration/tests.
        pass
    configured = bool(base and model and secret)
    eligible = configured and free
    return {
        "id": provider.key, "name": provider.label, "protocol": provider.protocol,
        "configured": configured, "free_confirmed": free, "eligible": eligible,
        "model": model if model else None,
        "base_url": base if base else None,
        "secret_env": provider.secret_env,
        "reason": None if eligible else (
            "Set base URL, model, API secret, and explicitly confirm this endpoint "
            "is currently free. Paid or unverified endpoints are blocked."
        ),
    }


def list_providers() -> list[dict[str, Any]]:
    return [{k: v for k, v in _provider_config(p).items() if k not in {"base_url", "secret_env"}}
            for p in PROVIDERS]


def _resolve(provider_id: str) -> tuple[Provider, dict[str, Any]]:
    provider = next((p for p in PROVIDERS if p.key == provider_id), None)
    if provider is None:
        raise ValueError("Unknown provider")
    config = _provider_config(provider)
    if not config["eligible"]:
        raise PermissionError(config["reason"])
    return provider, config


def _post(url: str, payload: dict[str, Any], headers: dict[str, str],
          timeout: int = 35) -> dict[str, Any]:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(1_000_000).decode("utf-8")
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        # Provider response bodies can echo request data or credential material.
        # Keep owner-facing errors useful without returning untrusted response text.
        raise RuntimeError(f"Provider returned HTTP {exc.code}. Check server-side provider logs.") from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Provider connection failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("Provider returned invalid JSON") from exc


def generate(provider_id: str, prompt: str) -> dict[str, Any]:
    provider, config = _resolve(provider_id)
    base = os.getenv(provider.base_url_env, "").strip().rstrip("/")
    model = os.getenv(provider.model_env, "").strip()
    secret = os.getenv(provider.secret_env, "").strip()
    try:
        from ai_os.credential_vault import PROVIDER_META, get_provider_secret
        if provider.key in PROVIDER_META:
            saved = get_provider_secret(provider.key)
            if saved:
                model, secret, _free = saved
                base = PROVIDER_META[provider.key]["base_url"]
    except Exception as exc:
        raise RuntimeError("Could not load encrypted provider credentials.") from exc
    started = time.monotonic()

    if provider.protocol == "gemini":
        url = f"{base}/v1beta/models/{model}:generateContent"
        data = _post(url, {"contents": [{"parts": [{"text": prompt}]}]},
                     {"x-goog-api-key": secret}, timeout=45)
        candidates = data.get("candidates") or []
        parts = ((candidates[0].get("content") or {}).get("parts") or []) if candidates else []
        answer = "\n".join(str(p.get("text", "")) for p in parts).strip()
        if not answer:
            raise RuntimeError("Gemini returned no text content")
    elif provider.protocol == "cloudflare":
        url = f"{base}/{model}"
        data = _post(url, {"messages": [{"role": "user", "content": prompt}]},
                     {"Authorization": f"Bearer {secret}"}, timeout=45)
        answer = str(data.get("result", {}).get("response", "")).strip()
        if not answer:
            raise RuntimeError("Cloudflare returned no text content")
    else:
        url = f"{base}/chat/completions"
        data = _post(url, {
            "model": model, "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2, "max_tokens": 512
        }, {"Authorization": f"Bearer {secret}"}, timeout=45)
        choices = data.get("choices") or []
        answer = str((choices[0].get("message") or {}).get("content", "")).strip() if choices else ""
        if not answer:
            raise RuntimeError("Provider returned no text content")

    return {
        "provider": provider.key, "model": model, "response": answer,
        "latency_ms": round((time.monotonic() - started) * 1000),
        "cost_guard": "free-confirmed-by-owner; provider limits still apply",
        "live": True,
    }


def test_provider(provider_id: str) -> dict[str, Any]:
    result = generate(provider_id, "Reply with exactly: AIOS live connection successful")
    result["test_passed"] = result["response"].strip().lower().startswith(
        "aios live connection successful"
    )
    return result
