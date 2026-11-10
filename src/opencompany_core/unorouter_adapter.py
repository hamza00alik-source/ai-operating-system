"""UnoRouter free-model adapter for the independent OpenCompany runtime.

This adapter sends requests only to UnoRouter's OpenAI-compatible chat endpoint.
It is enabled only by an explicit server-side owner configuration and a model
ID ending in :free. It never chooses a paid route or performs paid fallback.
"""
from __future__ import annotations

import json
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
MAX_RESPONSE_BYTES = 2_000_000


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
            if cost < 0:
                raise ValueError("negative provider cost")
        except (KeyError, IndexError, TypeError, ValueError, UnicodeDecodeError) as exc:
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
            input_tokens=int(input_tokens) if input_tokens is not None else None,
            output_tokens=int(output_tokens) if output_tokens is not None else None,
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
