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

from ai_os.credentials import get_provider_credential


class ProviderHTTPError(RuntimeError):
    """An upstream HTTP failure with a safe status code for routing decisions."""
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        super().__init__(f"Provider HTTP {status_code}: {detail[:1200]}")


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
    Provider("openrouter", "OpenRouter", "AI_OS_OPENROUTER_BASE_URL", "AI_OS_OPENROUTER_MODEL",
             "AI_OS_OPENROUTER_API_KEY", "AI_OS_OPENROUTER_FREE_CONFIRMED"),
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
    saved = get_provider_credential(provider.key)
    if saved:
        base, model, secret = saved["base_url"], saved["model"], saved["secret"]
        free = saved["free_confirmed"]
    configured = bool(base and model and secret)
    eligible = configured and free
    return {
        "id": provider.key, "name": provider.label, "protocol": provider.protocol,
        "_secret": secret,
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
    return [{k: v for k, v in _provider_config(p).items()
             if k not in {"base_url", "secret_env", "_secret"}}
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
        detail = exc.read(2000).decode("utf-8", errors="replace")
        raise ProviderHTTPError(exc.code, detail) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Provider connection failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("Provider returned invalid JSON") from exc


def generate(provider_id: str, prompt: str) -> dict[str, Any]:
    provider, config = _resolve(provider_id)
    base = config.get("base_url") or os.getenv(provider.base_url_env, "").strip().rstrip("/")
    model = config.get("model") or os.getenv(provider.model_env, "").strip()
    secret = config.get("_secret") or os.getenv(provider.secret_env, "").strip()
    started = time.monotonic()

    if provider.protocol == "gemini":
        url = f"{base}/v1beta/models/{model}:generateContent?key={secret}"
        data = _post(url, {"contents": [{"parts": [{"text": prompt}]}]},
                     {}, timeout=45)
        candidates = data.get("candidates") or []
        parts = ((candidates[0].get("content") or {}).get("parts") or []) if candidates else []
        answer = "\n".join(str(p.get("text", "")) for p in parts).strip()
        usage = data.get("usageMetadata") or {}
        input_tokens = usage.get("promptTokenCount")
        output_tokens = usage.get("candidatesTokenCount")
    elif provider.protocol == "cloudflare":
        url = f"{base}/{model}"
        data = _post(url, {"messages": [{"role": "user", "content": prompt}]},
                     {"Authorization": f"Bearer {secret}"}, timeout=45)
        answer = str(data.get("result", {}).get("response", "")).strip()
        usage = data.get("result", {}).get("usage") or {}
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
    else:
        url = f"{base}/chat/completions"
        headers = {"Authorization": f"Bearer {secret}"}
        if provider.protocol == "openai" and provider.key == "openrouter":
            headers.update({
                "HTTP-Referer": os.getenv("AI_OS_OPENROUTER_REFERER", "https://github.com/hamza00alik-source/ai-operating-system"),
                "X-Title": "AI Operating System",
            })
        data = _post(url, {
            "model": model, "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2, "max_tokens": 1200
        }, headers, timeout=45)
        choices = data.get("choices") or []
        answer = str((choices[0].get("message") or {}).get("content", "")).strip() if choices else ""
        usage = data.get("usage") or {}
        input_tokens = usage.get("prompt_tokens")
        output_tokens = usage.get("completion_tokens")

    if not answer or answer.casefold() in {"none", "null", "n/a", "[]", "{}"} or len(answer) < 24:
        raise RuntimeError(f"{provider.label} returned empty or placeholder text; refusing to mark this agent stage complete")

    return {
        "provider": provider.key, "model": data.get("model", model), "response": answer,
        "latency_ms": round((time.monotonic() - started) * 1000),
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": usage.get("total_tokens") if isinstance(usage, dict) else None,
            "reported_by_provider": bool(input_tokens is not None or output_tokens is not None),
        },
        "cost_guard": "free-confirmed-by-owner; provider limits still apply",
        "live": True,
    }



def generate_with_fallback(prompt: str, preferred_provider: str = "openrouter") -> dict[str, Any]:
    """Use the preferred free-confirmed provider first, then other eligible providers.

    Fallback is restricted to providers explicitly configured and owner-confirmed
    as free. No paid route, billing upgrade, or hidden retry is ever attempted.
    """
    preferred = next((p for p in PROVIDERS if p.key == preferred_provider), None)
    if preferred is None:
        raise ValueError("Unknown preferred provider")

    eligible = [p for p in PROVIDERS if _provider_config(p)["eligible"]]
    ordered = ([preferred] if preferred in eligible else []) + [
        p for p in eligible if p.key != preferred_provider
    ]
    if not ordered:
        raise PermissionError(
            "No free-confirmed providers are configured. Connect and verify a free provider in the owner console."
        )

    attempts: list[dict[str, Any]] = []
    retryable_statuses = {401, 402, 403, 404, 408, 409, 425, 429, 500, 502, 503, 504}
    last_error: Exception | None = None
    for provider in ordered:
        try:
            result = generate(provider.key, prompt)
            attempts.append({"provider": provider.key, "status": "success"})
            result["preferred_provider"] = preferred_provider
            result["fallback_used"] = provider.key != preferred_provider
            result["provider_attempts"] = attempts
            return result
        except ProviderHTTPError as exc:
            attempts.append({"provider": provider.key, "status": "unavailable", "http_status": exc.status_code})
            last_error = exc
            if exc.status_code not in retryable_statuses:
                raise
        except RuntimeError as exc:
            # Empty/placeholder model output is an upstream provider failure too.
            # Try the next explicitly free-confirmed provider; never accept the
            # bad response as a completed stage and never route to paid providers.
            message = str(exc).casefold()
            if "returned empty or placeholder text" in message:
                attempts.append({"provider": provider.key, "status": "invalid_or_empty_output"})
            else:
                attempts.append({"provider": provider.key, "status": "connection_or_response_error"})
            last_error = exc

    detail = str(last_error)[:700] if last_error else "No provider returned a usable response."
    # Include provider IDs and HTTP statuses, but never credentials or request headers,
    # so the owner can identify which upstream rejected the request.
    attempt_summary = "; ".join(
        f"{item['provider']}: {item.get('status', 'unknown')}"
        + (f" (HTTP {item['http_status']})" if item.get("http_status") else "")
        for item in attempts
    )
    raise RuntimeError(
        "All configured free-confirmed providers were unavailable. "
        + detail
        + " Provider attempts: " + (attempt_summary or "none recorded") + "."
        + " No paid fallback was attempted. Check the named provider's status, model access, and quota."
    )



def test_provider(provider_id: str) -> dict[str, Any]:
    result = generate(provider_id, "Reply with exactly: AIOS live connection successful")
    result["test_passed"] = result["response"].strip().lower().startswith(
        "aios live connection successful"
    )
    return result
