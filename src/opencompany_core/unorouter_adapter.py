"""UnoRouter free-model adapter for the independent OpenCompany runtime.

This adapter sends requests only to UnoRouter's OpenAI-compatible chat endpoint.
It is enabled only by an explicit server-side owner configuration and a model
ID ending in :free. It never chooses a paid route or performs paid fallback.
"""
from __future__ import annotations

import json
import math
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .model_gateway import (
    BillingMode,
    ModelRequest,
    ModelResult,
    ProviderPolicy,
    ProviderUnavailable,
)

UNOROUTER_BASE_URL = "https://api.unorouter.com/v1"
UNOROUTER_TIMEOUT_SECONDS = 45
MAX_RESPONSE_BYTES = 4_000_000
UNOROUTER_MODELS_URL = f"{UNOROUTER_BASE_URL}/models"
UNOROUTER_PRICING_CATALOG_URL = "https://api.unorouter.com/api/pricing/catalog"
UNOROUTER_CATALOG_TIMEOUT_SECONDS = 20


def _read_json_url(url: str, *, api_key: str | None = None) -> dict:
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    outbound = Request(url, headers=headers, method="GET")
    try:
        with urlopen(outbound, timeout=UNOROUTER_CATALOG_TIMEOUT_SECONDS) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ProviderUnavailable("UnoRouter model catalogue exceeded the configured size limit.")
    except HTTPError as exc:
        if api_key and exc.code in {401, 403}:
            raise ProviderUnavailable("UnoRouter rejected the API key or its model-list permission.") from exc
        raise ProviderUnavailable(f"UnoRouter catalogue request returned HTTP {exc.code}.") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise ProviderUnavailable(f"UnoRouter catalogue connection failed ({type(exc).__name__}).") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderUnavailable("UnoRouter returned an invalid model catalogue response.") from exc
    if not isinstance(payload, dict):
        raise ProviderUnavailable("UnoRouter returned an unexpected model catalogue shape.")
    return payload


def discover_free_models(api_key: str) -> list[dict[str, object]]:
    """Return only models both allowed by this API key and explicitly free/online in pricing."""
    key = api_key.strip()
    if not key or len(key) > 512:
        raise ValueError("A valid UnoRouter API key is required.")

    allowed_payload = _read_json_url(UNOROUTER_MODELS_URL, api_key=key)
    allowed_models = allowed_payload.get("data")
    if allowed_models is None:
        allowed_models = allowed_payload.get("models")
    if not isinstance(allowed_models, list):
        raise ProviderUnavailable("UnoRouter did not return a valid model list for this API key.")

    catalog_payload = _read_json_url(UNOROUTER_PRICING_CATALOG_URL)
    catalog_models = catalog_payload.get("models")
    if not isinstance(catalog_models, list):
        raise ProviderUnavailable("UnoRouter pricing catalogue did not contain a valid model list.")

    free_catalog: dict[str, dict] = {}
    for entry in catalog_models:
        if not isinstance(entry, dict) or entry.get("is_free") is not True or entry.get("online") is not True:
            continue
        model_name = entry.get("model_name")
        input_price, output_price = entry.get("input_price"), entry.get("output_price")
        if not isinstance(model_name, str) or not model_name.strip():
            continue
        if (isinstance(input_price, bool) or isinstance(output_price, bool)
                or not isinstance(input_price, (int, float))
                or not isinstance(output_price, (int, float))
                or not math.isfinite(float(input_price)) or not math.isfinite(float(output_price))
                or float(input_price) != 0.0 or float(output_price) != 0.0):
            continue
        normalized = model_name.strip()
        free_catalog[normalized] = entry
        free_catalog[normalized.removesuffix(":free")] = entry

    discovered: dict[str, dict[str, object]] = {}
    for item in allowed_models:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id")
        if not isinstance(model_id, str):
            continue
        model_id = model_id.strip()
        if not model_id.endswith(":free"):
            continue
        pricing = free_catalog.get(model_id) or free_catalog.get(model_id.removesuffix(":free"))
        if pricing is None:
            continue
        discovered[model_id] = {
            "id": model_id,
            "name": model_id,
            "vendor": str(pricing.get("vendor") or ""),
            "context_length": item.get("context_length") if isinstance(item.get("context_length"), int) else None,
            "max_output_tokens": item.get("max_output_tokens") if isinstance(item.get("max_output_tokens"), int) else None,
        }
    return sorted(discovered.values(), key=lambda model: str(model["id"]).casefold())


class UnoRouterAdapter:
    """Small bounded OpenAI-compatible transport; credentials remain server-side."""

    def __init__(self, api_key: str, *, timeout: int = UNOROUTER_TIMEOUT_SECONDS) -> None:
        if not api_key or len(api_key) > 512:
            raise ValueError("a valid UnoRouter API key is required")
        if not 1 <= timeout <= 120:
            raise ValueError("timeout must be between 1 and 120 seconds")
        self._api_key = api_key
        self._timeout = timeout

    def generate(self, request: ModelRequest, *, model: str) -> ModelResult:
        if not model.endswith(":free"):
            raise ProviderUnavailable("UnoRouter automatic routing accepts only explicitly free model IDs.")
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
            # Do not include response bodies: they can contain provider diagnostics or sensitive data.
            raise ProviderUnavailable(f"UnoRouter returned HTTP {exc.code}.") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ProviderUnavailable(f"UnoRouter connection failed ({type(exc).__name__}).") from exc

        try:
            decoded = json.loads(raw.decode("utf-8"))
            choices = decoded["choices"]
            text = choices[0]["message"]["content"]
            if isinstance(text, list):
                text = "".join(
                    part.get("text", "") for part in text if isinstance(part, dict)
                )
            text = str(text).strip()
            returned_model = str(decoded.get("model") or model)
            usage = decoded.get("usage") or {}
            input_tokens = usage.get("prompt_tokens")
            output_tokens = usage.get("completion_tokens")
            reported_cost = usage.get("cost", decoded.get("cost"))
            if reported_cost is None:
                raise ValueError("provider did not explicitly report request cost")
            cost = float(reported_cost)
            if not math.isfinite(cost) or cost < 0:
                raise ValueError("provider cost must be finite and non-negative")
            input_tokens = int(input_tokens) if input_tokens is not None else None
            output_tokens = int(output_tokens) if output_tokens is not None else None
            if (input_tokens is not None and input_tokens < 0) or (output_tokens is not None and output_tokens < 0):
                raise ValueError("provider token usage must be non-negative")
        except (AttributeError, KeyError, IndexError, TypeError, ValueError, UnicodeDecodeError) as exc:
            raise ProviderUnavailable("UnoRouter returned an invalid chat-completion response.") from exc

        if returned_model != model:
            raise ProviderUnavailable("UnoRouter returned a different model than the locked free model.")
        if not text:
            raise ProviderUnavailable("UnoRouter returned an empty completion.")
        return ModelResult(
            text=text,
            provider="unorouter",
            model=model,
            cost_usd=cost,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


def configured_unorouter_provider(configuration: dict[str, str] | None = None) -> tuple[ProviderPolicy, UnoRouterAdapter] | None:
    """Return the explicitly owner-enabled free provider, otherwise None.

    Required environment variables:
      OPENCOMPANY_UNOROUTER_API_KEY
      OPENCOMPANY_UNOROUTER_FREE_MODEL (must end in :free)
      OPENCOMPANY_CONFIRM_UNOROUTER_FREE=true
    """
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
    if not api_key or not model or not model.endswith(":free") or confirmation != "true":
        return None
    policy = ProviderPolicy(
        name="unorouter",
        model=model,
        billing_mode=BillingMode.FREE_CONFIRMED,
        max_cost_per_request_usd=0.0,
        priority=10,
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
    configured = bool(api_key and model.endswith(":free") and confirmation == "true")
    partial = bool(api_key or model or confirmation) and not configured
    return {
        "configured": configured,
        "model": model if configured else None,
        "billing_mode": "free_confirmed" if configured else "disabled",
        "partial_configuration_detected": partial,
        "automatic_paid_fallback": False,
    }
