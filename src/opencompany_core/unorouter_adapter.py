"""UnoRouter adapter with automatic discovery and rotation across every free model.

The automatic catalogue is the intersection of UnoRouter's live public pricing
catalogue and the models exposed to the owner's API key. Only online catalogue
entries with a key-visible :free model ID are eligible. The public base-row
is_free flag does not determine whether a separate :free variant exists. No paid fallback exists.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .model_gateway import BillingMode, ModelRequest, ModelResult, ProviderPolicy, ProviderUnavailable

UNOROUTER_BASE_URL = "https://api.unorouter.com/v1"
UNOROUTER_CATALOG_URL = "https://api.unorouter.com/api/pricing/catalog"
UNOROUTER_AUTO_FREE_MODEL = "unorouter/free-catalog:free"
UNOROUTER_TIMEOUT_SECONDS = 15
MAX_RESPONSE_BYTES = 2_000_000
CATALOG_CACHE_SECONDS = 300
_catalog_lock = threading.Lock()
_catalog_cache: dict[str, tuple[float, tuple[str, ...]]] = {}
_round_robin_lock = threading.Lock()
_round_robin_index = 0


def _read_json(url: str, *, api_key: str | None = None, timeout: int = 12) -> dict:
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ProviderUnavailable("UnoRouter catalogue response exceeded the configured size limit.")
    except HTTPError as exc:
        if api_key and exc.code in {401, 403}:
            raise ProviderUnavailable(
                "UnoRouter rejected this credential. Use the inference API key from the Tokens page (usually starts with sk-), not the separate account API-access token."
            ) from exc
        raise ProviderUnavailable(f"UnoRouter catalogue returned HTTP {exc.code}.") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise ProviderUnavailable(f"UnoRouter catalogue connection failed ({type(exc).__name__}).") from exc
    try:
        decoded = json.loads(raw.decode("utf-8"))
        if not isinstance(decoded, dict):
            raise ValueError("catalogue response is not an object")
        return decoded
    except (ValueError, UnicodeDecodeError) as exc:
        raise ProviderUnavailable("UnoRouter returned an invalid catalogue response.") from exc


def discover_model_catalog(api_key: str) -> tuple[dict[str, object], ...]:
    """Import the complete public catalogue, annotating account access and strict free-only eligibility.

    Paid and unsupported entries are retained as research metadata but are never
    returned as selectable inference routes.
    """
    if not api_key or len(api_key) > 512:
        raise ValueError("a valid UnoRouter API key is required")
    pricing = _read_json(UNOROUTER_CATALOG_URL)
    available = _read_json(f"{UNOROUTER_BASE_URL}/models", api_key=api_key)
    catalog_models = pricing.get("models")
    key_models = available.get("data")
    if not isinstance(catalog_models, list) or not isinstance(key_models, list):
        raise ProviderUnavailable("UnoRouter did not return the expected pricing catalogue or key-access model-list format.")
    key_ids = {
        item["id"].strip() for item in key_models
        if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"].strip()
    }
    imported = []
    for item in catalog_models:
        if not isinstance(item, dict):
            continue
        model_id = item.get("model_name")
        if not isinstance(model_id, str) or not model_id.strip():
            continue
        model_id = model_id.strip()
        endpoints = item.get("supported_endpoint_types")
        endpoints = [str(value).strip().casefold() for value in endpoints] if isinstance(endpoints, list) else []
        input_price = item.get("input_price")
        output_price = item.get("output_price")
        fixed_price = item.get("fixed_price")
        zero_priced = (
            all(isinstance(value, (int, float)) and math.isfinite(float(value)) and float(value) == 0.0 for value in (input_price, output_price))
            and (fixed_price is None or isinstance(fixed_price, (int, float)) and math.isfinite(float(fixed_price)) and float(fixed_price) == 0.0)
        )
        is_free = item.get("is_free") is True
        route_model_id = model_id if model_id.endswith(":free") or not is_free else model_id + ":free"
        account_access = route_model_id in key_ids or (not is_free and model_id in key_ids)
        type_supported = item.get("type") in (None, "text")
        chat_supported = item.get("chat") is not False
        endpoint_supported = not endpoints or "openai" in endpoints
        strict_free = (
            is_free and zero_priced and route_model_id.endswith(":free")
            and item.get("online") is True and type_supported
            and chat_supported and endpoint_supported and route_model_id in key_ids
        )
        if strict_free:
            reason = "eligible_free"
        elif not account_access:
            reason = "not_available_to_api_key"
        elif item.get("online") is not True:
            reason = "offline"
        elif not type_supported or not chat_supported or not endpoint_supported:
            reason = "unsupported_for_chat_inference"
        elif not (item.get("is_free") is True and zero_priced and model_id.endswith(":free")):
            reason = "paid_or_unverified_pricing"
        else:
            reason = "blocked_by_free_only_policy"
        # Keep a safe, useful subset; do not persist credentials or arbitrary upstream fields.
        imported.append({
            "model_id": route_model_id,
            "vendor": str(item.get("vendor") or "Unknown"),
            "vendor_id": item.get("vendor_id") if isinstance(item.get("vendor_id"), int) else None,
            "icon": str(item.get("icon") or ""),
            "type": str(item.get("type") or "unknown"),
            "release_ts": item.get("release_ts") if isinstance(item.get("release_ts"), int) else None,
            "tags": [str(tag) for tag in item.get("tags", []) if isinstance(tag, str)] if isinstance(item.get("tags"), list) else [],
            "online": item.get("online") is True,
            "chat": item.get("chat") is True,
            "is_free": item.get("is_free") is True,
            "input_price": input_price if isinstance(input_price, (int, float)) else None,
            "output_price": output_price if isinstance(output_price, (int, float)) else None,
            "fixed_price": fixed_price if isinstance(fixed_price, (int, float)) else None,
            "original_input_price": item.get("original_input_price") if isinstance(item.get("original_input_price"), (int, float)) else None,
            "original_output_price": item.get("original_output_price") if isinstance(item.get("original_output_price"), (int, float)) else None,
            "original_fixed_price": item.get("original_fixed_price") if isinstance(item.get("original_fixed_price"), (int, float)) else None,
            "is_fixed_price": item.get("is_fixed_price") is True,
            "own_purpose": {
                "trains_or_retains": item.get("own_purpose", {}).get("trains_or_retains"),
                "consent_required": item.get("own_purpose", {}).get("consent_required"),
                "countries": [str(country) for country in item.get("own_purpose", {}).get("countries", []) if isinstance(country, str)],
            } if isinstance(item.get("own_purpose"), dict) else None,
            "uptime_24h": item.get("uptime_24h") if isinstance(item.get("uptime_24h"), (int, float)) else None,
            "success_rate": item.get("success_rate") if isinstance(item.get("success_rate"), (int, float)) else None,
            "avg_latency_ms": item.get("avg_latency_ms") if isinstance(item.get("avg_latency_ms"), (int, float)) else None,
            "supported_endpoint_types": endpoints,
            "account_access": account_access,
            "allowed_for_inference": strict_free,
            "policy_status": reason,
        })
    return tuple(imported)


def discover_free_models(api_key: str, *, force_refresh: bool = False) -> tuple[str, ...]:
    """Return only models proven free, online, chat-capable, and accessible to this key."""
    if not api_key or len(api_key) > 512:
        raise ValueError("a valid UnoRouter API key is required")
    now = time.monotonic()
    cache_key = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    with _catalog_lock:
        cached = _catalog_cache.get(cache_key)
        if cached and not force_refresh and now - cached[0] < CATALOG_CACHE_SECONDS:
            return cached[1]
    catalog = discover_model_catalog(api_key)
    models = tuple(sorted(
        str(item["model_id"]) for item in catalog
        if item.get("allowed_for_inference") is True
    ))
    if not models:
        raise ProviderUnavailable(
            "No models were confirmed free, zero-priced, online, chat-capable, and accessible to this UnoRouter key."
        )
    with _catalog_lock:
        _catalog_cache[cache_key] = (time.monotonic(), models)
    return models


class UnoRouterAdapter:
    """Bounded OpenAI-compatible transport; credentials remain server-side."""

    def __init__(self, api_key: str, *, timeout: int = UNOROUTER_TIMEOUT_SECONDS) -> None:
        if not api_key or len(api_key) > 512:
            raise ValueError("a valid UnoRouter API key is required")
        if not 1 <= timeout <= 120:
            raise ValueError("timeout must be between 1 and 120 seconds")
        self._api_key = api_key
        self._timeout = timeout

    def _generate_one(self, request: ModelRequest, *, model: str) -> ModelResult:
        if not model.endswith(":free"):
            raise ProviderUnavailable("UnoRouter accepts only explicitly free model IDs.")
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": request.prompt}],
            "max_tokens": request.max_output_tokens,
            "stream": False,
        }
        outbound = Request(
            f"{UNOROUTER_BASE_URL}/chat/completions",
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(outbound, timeout=self._timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise ProviderUnavailable("UnoRouter response exceeded the configured size limit.")
        except HTTPError as exc:
            raise ProviderUnavailable(f"UnoRouter returned HTTP {exc.code}.") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ProviderUnavailable(f"UnoRouter connection failed ({type(exc).__name__}).") from exc

        try:
            decoded = json.loads(raw.decode("utf-8"))
            choices = decoded["choices"]
            text = choices[0]["message"]["content"]
            if isinstance(text, list):
                text = "".join(part.get("text", "") for part in text if isinstance(part, dict))
            text = str(text).strip()
            returned_model = str(decoded.get("model") or model)
            usage = decoded.get("usage") or {}
            input_tokens = usage.get("prompt_tokens")
            output_tokens = usage.get("completion_tokens")
            reported_cost = usage.get("cost", decoded.get("cost"))
            # A :free model ID is not transaction-level billing evidence.
            # Fail closed when the provider omits cost; never infer zero from
            # the route name or catalogue metadata.
            if reported_cost is None:
                raise ValueError("provider omitted transaction cost; zero-cost usage cannot be verified")
            cost = float(reported_cost)
            if not math.isfinite(cost) or cost < 0:
                raise ValueError("provider cost must be finite and non-negative")
            input_tokens = int(input_tokens) if input_tokens is not None else None
            output_tokens = int(output_tokens) if output_tokens is not None else None
            if (input_tokens is not None and input_tokens < 0) or (output_tokens is not None and output_tokens < 0):
                raise ValueError("provider token usage must be non-negative")
        except (AttributeError, KeyError, IndexError, TypeError, ValueError, UnicodeDecodeError) as exc:
            if "transaction cost" in str(exc):
                raise ProviderUnavailable("UnoRouter omitted transaction cost in an invalid chat-completion response.") from exc
            raise ProviderUnavailable("UnoRouter returned an invalid chat-completion response.") from exc

        if returned_model not in {model, model.removesuffix(":free")}:
            raise ProviderUnavailable("UnoRouter returned a different model than the requested free variant.")
        if not text:
            raise ProviderUnavailable("UnoRouter returned an empty completion.")
        return ModelResult(
            text=text, provider="unorouter", model=model, cost_usd=cost,
            input_tokens=input_tokens, output_tokens=output_tokens,
        )

    def generate(self, request: ModelRequest, *, model: str) -> ModelResult:
        if model != UNOROUTER_AUTO_FREE_MODEL:
            return self._generate_one(request, model=model)

        models = discover_free_models(self._api_key)
        global _round_robin_index
        with _round_robin_lock:
            start = _round_robin_index % len(models)
            _round_robin_index += 1
        ordered = models[start:] + models[:start]
        failures = []
        for candidate in ordered:
            try:
                return self._generate_one(request, model=candidate)
            except ProviderUnavailable as exc:
                failures.append(f"{candidate}: {exc}")
                # 429, offline upstream, or model retirement: try another
                # confirmed-free model. Any non-zero cost is rejected by the
                # gateway and is never retried through a paid route.
                continue
        raise ProviderUnavailable("All discovered free UnoRouter models were unavailable: " + "; ".join(failures[:8]))


def configured_unorouter_provider(configuration: dict[str, str] | None = None):
    """Return the owner-enabled free catalogue route or one explicit free model."""
    if configuration is not None:
        api_key = str(configuration.get("api_key", "")).strip()
        model = str(configuration.get("model", "")).strip()
        confirmation = "true" if configuration.get("confirmed_free") == "true" else ""
    else:
        api_key = os.environ.get("OPENCOMPANY_UNOROUTER_API_KEY", "").strip()
        model = os.environ.get("OPENCOMPANY_UNOROUTER_FREE_MODEL", "").strip()
        confirmation = os.environ.get("OPENCOMPANY_CONFIRM_UNOROUTER_FREE", "").strip().lower()
    if not (api_key or model or confirmation):
        return None
    if not api_key or not (model == UNOROUTER_AUTO_FREE_MODEL or model.endswith(":free")) or confirmation != "true":
        return None
    policy = ProviderPolicy(
        name="unorouter", model=model, billing_mode=BillingMode.FREE_CONFIRMED,
        max_cost_per_request_usd=0.0, priority=10,
    )
    return policy, UnoRouterAdapter(api_key)


def configured_unorouter_gateway(configuration: dict[str, str] | None = None):
    """Build a gateway using encrypted owner settings or explicit environment settings."""
    from .model_gateway import ModelGateway
    configured = configured_unorouter_provider(configuration)
    return ModelGateway.configure((configured,)) if configured is not None else ModelGateway()


def unorouter_configuration_status(configuration: dict[str, str] | None = None) -> dict[str, object]:
    if configuration is not None:
        api_key = str(configuration.get("api_key", "")).strip()
        model = str(configuration.get("model", "")).strip()
        confirmation = "true" if configuration.get("confirmed_free") == "true" else ""
    else:
        api_key = os.environ.get("OPENCOMPANY_UNOROUTER_API_KEY", "").strip()
        model = os.environ.get("OPENCOMPANY_UNOROUTER_FREE_MODEL", "").strip()
        confirmation = os.environ.get("OPENCOMPANY_CONFIRM_UNOROUTER_FREE", "").strip().lower()
    configured = bool(api_key and (model == UNOROUTER_AUTO_FREE_MODEL or model.endswith(":free")) and confirmation == "true")
    partial = bool(api_key or model or confirmation) and not configured
    return {
        "configured": configured,
        "model": model if configured else None,
        "routing_mode": "automatic_all_free_models" if model == UNOROUTER_AUTO_FREE_MODEL and configured else "single_model",
        "billing_mode": "free_confirmed" if configured else "disabled",
        "partial_configuration_detected": partial,
        "automatic_paid_fallback": False,
    }
