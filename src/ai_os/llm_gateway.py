"""Zero-cost guarded LLM gateway.

Only explicitly configured providers marked as free are eligible. Secrets are read
from server environment variables and are never returned by status endpoints.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from ai_os.credentials import get_provider_credential


_UNO_CATALOG_CACHE: dict[str, Any] = {"fingerprint": None, "expires_at": 0.0, "catalog": None}
_UNO_CATALOG_LOCK = threading.Lock()
_UNO_CATALOG_TTL_SECONDS = 300


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
    experimental_only: bool = False


PROVIDERS = (
    Provider("gemini", "Google Gemini", "AI_OS_GEMINI_BASE_URL", "AI_OS_GEMINI_MODEL",
             "AI_OS_GEMINI_API_KEY", "AI_OS_GEMINI_FREE_CONFIRMED", "gemini"),
    Provider("openrouter", "OpenRouter", "AI_OS_OPENROUTER_BASE_URL", "AI_OS_OPENROUTER_MODEL",
             "AI_OS_OPENROUTER_API_KEY", "AI_OS_OPENROUTER_FREE_CONFIRMED"),
    Provider("unorouter", "UnoRouter · primary free model gateway", "AI_OS_UNOROUTER_BASE_URL",
             "AI_OS_UNOROUTER_MODEL", "AI_OS_UNOROUTER_API_KEY",
             "AI_OS_UNOROUTER_FREE_CONFIRMED", ),
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
    # Only an explicit OpenRouter :free route is admitted to unattended AIOS
    # company inference. A dashboard checkbox is not proof that an arbitrary
    # provider/model is zero-cost, so every other legacy provider is fail-closed.
    verified_free_model = (
        provider.key == "openrouter"
        and base == "https://openrouter.ai/api/v1"
        and model.endswith(":free")
    )
    company_route_allowed = verified_free_model
    eligible = (
        configured and free and verified_free_model and not provider.experimental_only
        and company_route_allowed
    )
    return {
        "id": provider.key, "name": provider.label, "protocol": provider.protocol,
        "_secret": secret,
        "configured": configured, "free_confirmed": free, "eligible": eligible,
        "experimental_only": provider.experimental_only,
        "model": model if model else None,
        "base_url": base if base else None,
        "secret_env": provider.secret_env,
        "reason": None if eligible else (
            "Only an explicitly free OpenRouter model ID ending in :free is enabled for company inference. Other providers remain disabled until zero-cost routing can be independently verified."
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


def _assert_zero_cost_model_response(data: dict[str, Any], requested_model: str) -> None:
    """Reject model substitution and any reported non-zero/non-finite charge."""
    returned_model = str(data.get("model") or requested_model)
    if returned_model not in {requested_model, requested_model.removesuffix(":free")}:
        raise RuntimeError("Provider returned a different model than the requested free route.")
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    reported_cost = usage.get("cost", data.get("cost"))
    if reported_cost is not None:
        try:
            cost = float(reported_cost)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("Provider returned an invalid cost for a zero-cost route.") from exc
        if not math.isfinite(cost) or cost != 0.0:
            raise RuntimeError("Provider reported a non-zero cost for a zero-cost route.")


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



def list_unorouter_catalog() -> dict[str, Any]:
    """Read the public price catalog and exact models exposed to the saved API key.
    This is read-only discovery: it never submits a prompt or invokes inference.
    """
    public_url = "https://api.unorouter.com/api/pricing/catalog"
    request = urllib.request.Request(public_url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            public = json.loads(response.read(1_000_000).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ProviderHTTPError(exc.code, "UnoRouter public pricing catalog request failed") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("UnoRouter public catalog is temporarily unreachable") from exc
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise RuntimeError("UnoRouter returned an invalid public model catalog") from exc
    public_models = public.get("models", []) if isinstance(public, dict) else []
    prices = {}
    for item in public_models:
        if isinstance(item, dict) and item.get("model_name"):
            prices[str(item["model_name"]).strip()] = item
    saved = get_provider_credential("unorouter")
    available = []
    if saved:
        req = urllib.request.Request("https://api.unorouter.com/v1/models", headers={
            "Accept": "application/json", "Authorization": f"Bearer {saved['secret']}"
        })
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                payload = json.loads(response.read(1_000_000).decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise ProviderHTTPError(exc.code, "UnoRouter account model-list request failed") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError("UnoRouter account model list is temporarily unreachable") from exc
        except (json.JSONDecodeError, UnicodeError) as exc:
            raise RuntimeError("UnoRouter returned an invalid account model list") from exc
        if isinstance(payload, dict) and payload.get("success") is False:
            raise RuntimeError("UnoRouter rejected the account model-list request: " + str(payload.get("message") or "unknown error")[:300])
        data = payload.get("data", payload) if isinstance(payload, dict) else payload
        entries = data.get("data", data.get("models", [])) if isinstance(data, dict) else data
        if isinstance(entries, dict):
            entries = entries.get("items", [])
        for item in entries if isinstance(entries, list) else []:
            if not isinstance(item, dict):
                continue
            model_id = str(item.get("id") or item.get("model") or "").strip()
            if not model_id:
                continue
            is_free = model_id.endswith(":free")
            price_name = model_id[:-5] if is_free else model_id
            price = prices.get(price_name) or prices.get(model_id) or {}
            available.append({
                "id": model_id, "name": str(item.get("name") or price.get("model_name") or model_id),
                "vendor": price.get("vendor") or item.get("owned_by") or item.get("vendor"),
                "free": is_free, "online": price.get("online"),
                "input_price_per_million": 0 if is_free else price.get("input_price"),
                "output_price_per_million": 0 if is_free else price.get("output_price"),
                "currency": "USD", "callable": True,
                "context_length": item.get("context_length"),
                "max_output_tokens": item.get("max_output_tokens"),
                "supported_endpoint_types": price.get("supported_endpoint_types") or item.get("supported_endpoint_types") or [],
            })
        available.sort(key=lambda item: (not item["free"], str(item.get("vendor") or ""), item["id"]))
    public_summary = [{
        "name": str(item.get("model_name") or ""), "vendor": item.get("vendor"),
        "type": item.get("type"), "free": item.get("is_free") is True,
        "online": item.get("online") is True,
        "input_price_per_million": item.get("input_price"),
        "output_price_per_million": item.get("output_price"), "currency": "USD",
        "supported_endpoint_types": item.get("supported_endpoint_types") or [],
    } for item in public_models if isinstance(item, dict)]
    counts = public.get("counts") if isinstance(public, dict) and isinstance(public.get("counts"), dict) else {}
    return {
        "provider": "unorouter", "catalog_source": public_url,
        "account_models_source": "https://api.unorouter.com/v1/models" if saved else None,
        "account_key_configured": bool(saved), "counts": counts,
        "available_to_key_count": len(available),
        "available_free_count": sum(1 for item in available if item["free"]),
        "available_paid_count": sum(1 for item in available if not item["free"]),
        "models": available, "public_models": public_summary,
        "note": "Read-only catalogue lookup. Exact callable IDs come from authenticated /v1/models. :free models are zero-cost; other IDs are paid. No prompt or inference request is sent."
    }



def _task_category(prompt: str) -> str:
    """Classify the request with conservative keyword rules; no extra model call."""
    text = (prompt or "").casefold()
    rules = (
        ("coding", ("write code", "debug", "python", "javascript", "typescript", "sql", "api", "code review", "refactor", "implement", "programming", "function", "class ")),
        ("reasoning", ("prove", "solve", "reason", "step by step", "logic puzzle", "derive", "mathematical", "trade-off", "architecture decision")),
        ("research", ("research", "competitor", "market analysis", "compare sources", "evidence", "literature review", "investigate", "industry analysis")),
        ("creative", ("story", "creative", "brainstorm", "brand voice", "write a poem", "character concept", "slogan", "fiction")),
    )
    for category, terms in rules:
        if any(term in text for term in terms):
            return category
    return "general"


def _cached_unorouter_catalog() -> dict[str, Any]:
    saved = get_provider_credential("unorouter")
    if not saved or not saved.get("secret"):
        raise PermissionError("Save the UnoRouter API key before automatic model discovery.")
    fingerprint = hashlib.sha256(saved["secret"].encode("utf-8")).hexdigest()
    now = time.monotonic()
    with _UNO_CATALOG_LOCK:
        if (_UNO_CATALOG_CACHE["fingerprint"] == fingerprint
                and _UNO_CATALOG_CACHE["catalog"] is not None
                and _UNO_CATALOG_CACHE["expires_at"] > now):
            return _UNO_CATALOG_CACHE["catalog"]
    catalog = list_unorouter_catalog()
    with _UNO_CATALOG_LOCK:
        _UNO_CATALOG_CACHE.update(
            fingerprint=fingerprint,
            expires_at=now + _UNO_CATALOG_TTL_SECONDS,
            catalog=catalog,
        )
    return catalog


def _supports_chat_completions(model: dict[str, Any]) -> bool:
    """Exclude image/audio/embedding-only models from the text chat route."""
    endpoint_types = model.get("supported_endpoint_types") or []
    if isinstance(endpoint_types, str):
        endpoint_types = [endpoint_types]
    normalized = [str(value).casefold().replace("_", "-") for value in endpoint_types]
    return any(
        value in {"openai", "openai-compatible", "chat", "chat-completions",
                  "chat/completions", "text-generation"}
        or "chat" in value or "completion" in value
        for value in normalized
    )


def select_unorouter_model(prompt: str) -> dict[str, Any]:
    """Select an account-callable, explicitly :free chat model; discovery sends no prompt."""
    saved = get_provider_credential("unorouter")
    if not saved or not saved.get("free_confirmed"):
        raise PermissionError("UnoRouter free-only credentials are not owner-confirmed.")
    catalog = _cached_unorouter_catalog()
    models = [
        model for model in catalog.get("models", [])
        if isinstance(model, dict)
        and model.get("callable") is True
        and model.get("free") is True
        and str(model.get("id", "")).endswith(":free")
        and model.get("online") is not False
        and _supports_chat_completions(model)
    ]
    if not models:
        raise RuntimeError(
            "UnoRouter has no account-accessible :free model verified for chat completions. "
            "The selected dashboard model may support another modality; no prompt was sent."
        )

    category = _task_category(prompt)
    default_model = str(saved.get("model") or "")
    preference_terms = {
        "coding": ("coder", "codestral", "starcoder", "codeqwen", "devstral", "deepseek-coder"),
        "reasoning": ("deepseek-r1", "qwq", "reasoning", "thinking", "r1", "o1"),
        "research": ("sonar", "search", "long-context", "longcontext", "gpt-oss", "instruct"),
        "creative": ("creative", "writer", "llama", "mistral", "gemma", "qwen"),
        "general": ("instruct", "chat", "gpt-oss", "llama", "qwen", "mistral", "gemma"),
    }
    terms = preference_terms[category]

    def score(model: dict[str, Any]) -> tuple[int, int, int, str]:
        model_id = str(model.get("id", "")).casefold()
        vendor = str(model.get("vendor") or "").casefold()
        name = str(model.get("name") or "").casefold()
        identity = " ".join((model_id, vendor, name))
        points = sum(12 for term in terms if term in identity)
        if model.get("online") is True:
            points += 5
        if model.get("id") == default_model:
            points += 8
        try:
            context_score = min(int(model.get("context_length") or 0), 1_000_000)
        except (TypeError, ValueError):
            context_score = 0
        return (points, context_score, int(model.get("online") is True), str(model.get("id", "")))

    chosen = max(models, key=score)
    return {
        "task_category": category,
        "model_id": chosen["id"],
        "strategy": "account-accessible free chat models; metadata/name heuristic",
        "candidate_count": len(models),
        "benchmark_status": "not benchmarked; no extra inference calls made",
    }


def generate(provider_id: str, prompt: str) -> dict[str, Any]:
    provider, config = _resolve(provider_id)
    base = config.get("base_url") or os.getenv(provider.base_url_env, "").strip().rstrip("/")
    model = config.get("model") or os.getenv(provider.model_env, "").strip()
    secret = config.get("_secret") or os.getenv(provider.secret_env, "").strip()
    model_selection = None
    if provider.key == "unorouter":
        model_selection = select_unorouter_model(prompt)
        model = model_selection["model_id"]
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
        if provider.key == "openrouter":
            _assert_zero_cost_model_response(data, model)
        choices = data.get("choices") or []
        answer = str((choices[0].get("message") or {}).get("content", "")).strip() if choices else ""
        usage = data.get("usage") or {}
        input_tokens = usage.get("prompt_tokens")
        output_tokens = usage.get("completion_tokens")

    if not answer or answer.casefold() in {"none", "null", "n/a", "[]", "{}"} or len(answer) < 24:
        raise RuntimeError(f"{provider.label} returned empty or placeholder text; refusing to mark this agent stage complete")

    result = {
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
    if model_selection:
        result["model_selection"] = model_selection
    return result




def test_unorouter_personal(prompt: str) -> dict[str, Any]:
    """Owner-triggered consumer-account test; paid models are never permitted."""
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 12000:
        raise ValueError("Enter a test prompt of 1 to 12,000 characters.")
    config = get_provider_credential("unorouter")
    if not config or not config.get("secret"):
        raise PermissionError("Save a UnoRouter consumer API key in the owner console first.")
    if not config.get("free_confirmed"):
        raise PermissionError("UnoRouter free-only credentials are not owner-confirmed.")
    from opencompany_core.unorouter_adapter import discover_model_catalog
    catalog = discover_model_catalog(config["secret"])
    eligible = [item for item in catalog if item.get("allowed_for_inference") is True]
    if not eligible:
        raise PermissionError("No model is verified free, zero-priced, online, chat-capable, and accessible to this key. No prompt was sent.")
    model = str(eligible[0]["model_id"])
    base = (config.get("base_url") or "https://api.unorouter.com/v1").rstrip("/")
    started = time.monotonic()
    data = _post(
        f"{base}/chat/completions",
        {"model": model, "messages": [{"role": "user", "content": prompt}],
         "temperature": 0.2, "max_tokens": 800},
        {"Authorization": f"Bearer {config['secret']}"},
        timeout=45,
    )
    _assert_zero_cost_model_response(data, model)
    choices = data.get("choices") or []
    answer = str((choices[0].get("message") or {}).get("content", "")).strip() if choices else ""
    if not answer or answer.casefold() in {"none", "null", "n/a", "[]", "{}"} or len(answer) < 8:
        raise RuntimeError("UnoRouter returned empty or placeholder text.")
    usage = data.get("usage") or {}
    return {
        "provider": "unorouter", "model": data.get("model", model),
        "response": answer, "latency_ms": round((time.monotonic() - started) * 1000),
        "usage": {"input_tokens": usage.get("prompt_tokens"),
                  "output_tokens": usage.get("completion_tokens"),
                  "total_tokens": usage.get("total_tokens"),
                  "reported_by_provider": bool(usage)},
        "mode": "owner_personal_test_only",
        "model_cost_class": "free",
        "paid_request_approved": False,
        "company_task_routing": False,
        "warning": "Consumer-account test only. Paid models are blocked. Do not submit customer, company, confidential, or sensitive personal data. Provider/model-specific data terms apply.",
        "live": True,
    }


def generate_with_fallback(prompt: str, preferred_provider: str = "unorouter") -> dict[str, Any]:
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
