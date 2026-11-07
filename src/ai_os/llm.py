"""Opt-in OpenAI-compatible chat-completions client.

This adapter is deliberately not wired into API routes or background workers.
It makes no network request unless AI_OS_LLM_ENABLED=true is explicitly set.
No automatic provider fallback is performed: changing providers can change cost,
privacy, data residency, and terms, so that decision must remain explicit.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
import urllib.error
import urllib.request
from typing import Any


class LLMConfigurationError(RuntimeError):
    """Raised when the optional model integration is not safely configured."""


class LLMRequestError(RuntimeError):
    """Raised when a model provider request fails."""


@dataclass(frozen=True)
class LLMConfig:
    enabled: bool
    provider: str
    base_url: str
    model: str
    api_key: str
    timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "LLMConfig":
        try:
            timeout = float(os.getenv("AI_OS_LLM_TIMEOUT_SECONDS", "30"))
        except ValueError as exc:
            raise LLMConfigurationError("AI_OS_LLM_TIMEOUT_SECONDS must be numeric") from exc
        return cls(
            enabled=os.getenv("AI_OS_LLM_ENABLED", "").strip().lower() == "true",
            provider=os.getenv("AI_OS_LLM_PROVIDER", "").strip(),
            base_url=os.getenv("AI_OS_LLM_BASE_URL", "").strip().rstrip("/"),
            model=os.getenv("AI_OS_LLM_MODEL", "").strip(),
            api_key=os.getenv("AI_OS_LLM_API_KEY", "").strip(),
            timeout_seconds=timeout,
        )


def _validate(config: LLMConfig) -> None:
    if not config.enabled:
        raise LLMConfigurationError(
            "Model calls are disabled. Set AI_OS_LLM_ENABLED=true only after reviewing provider cost and terms."
        )
    if not all((config.provider, config.base_url, config.model, config.api_key)):
        raise LLMConfigurationError(
            "Configure AI_OS_LLM_PROVIDER, AI_OS_LLM_BASE_URL, AI_OS_LLM_MODEL, and AI_OS_LLM_API_KEY."
        )
    if config.timeout_seconds <= 0 or config.timeout_seconds > 180:
        raise LLMConfigurationError("Model request timeout must be between 0 and 180 seconds.")
    if not config.base_url.startswith("https://"):
        # Permit plain HTTP only for loopback-hosted local model servers.
        if not config.base_url.startswith(("http://localhost", "http://127.0.0.1", "http://[::1]")):
            raise LLMConfigurationError("Remote model endpoints must use HTTPS.")


def chat_completion(
    messages: list[dict[str, str]],
    *,
    config: LLMConfig | None = None,
    max_tokens: int | None = None,
) -> str:
    """Send one explicit chat-completion request and return assistant text.

    Callers must supply a provider key and explicitly enable this integration.
    This function does not retry, switch providers, log prompts, or persist keys.
    """
    settings = config or LLMConfig.from_env()
    _validate(settings)
    if not messages:
        raise LLMConfigurationError("At least one chat message is required.")
    if any(not isinstance(item, dict) or not isinstance(item.get("role"), str)
           or not isinstance(item.get("content"), str) for item in messages):
        raise LLMConfigurationError("Messages must contain string role and content fields.")
    payload: dict[str, Any] = {"model": settings.model, "messages": messages}
    if max_tokens is not None:
        if max_tokens < 1 or max_tokens > 32768:
            raise LLMConfigurationError("max_tokens must be between 1 and 32768.")
        payload["max_tokens"] = max_tokens

    request = urllib.request.Request(
        settings.base_url + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + settings.api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.timeout_seconds) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # Do not include provider response bodies, which may contain sensitive details.
        raise LLMRequestError(f"Model provider returned HTTP {exc.code}.") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LLMRequestError("Could not reach the configured model provider.") from None
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LLMRequestError("Model provider returned an invalid JSON response.") from None

    try:
        content = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise LLMRequestError("Model provider response did not contain assistant content.") from None
    if not isinstance(content, str):
        raise LLMRequestError("Model provider returned non-text assistant content.")
    return content
