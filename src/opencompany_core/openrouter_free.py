"""Strict OpenRouter free-model adapter with persistent quota protection.

The adapter can call only a fixed model identifier ending in ':free'. It has
no paid fallback and reserves quota before every outbound attempt.
"""
from __future__ import annotations

import json
from contextlib import closing
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .model_gateway import (
    BillingMode, ModelGateway, ModelRequest, ModelResult, ProviderPolicy,
    ProviderUnavailable,
)


class FreeQuotaExceeded(RuntimeError):
    pass


class SQLiteRequestQuota:
    """Process-safe daily and rolling-minute request reservation."""

    def __init__(self, path: str, *, daily_limit: int = 50, per_minute_limit: int = 20):
        if not 1 <= daily_limit <= 50 or not 1 <= per_minute_limit <= 20:
            raise ValueError("free-provider quotas cannot exceed published free limits")
        self.path = path
        self.daily_limit = daily_limit
        self.per_minute_limit = per_minute_limit
        self._lock = threading.Lock()
        with closing(self._connect()) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS provider_request_quota ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, provider TEXT NOT NULL, "
                "reserved_at REAL NOT NULL, utc_day TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_provider_quota_day "
                "ON provider_request_quota(provider, utc_day, reserved_at)"
            )

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def reserve(self, provider: str, *, now: float | None = None) -> None:
        timestamp = time.time() if now is None else now
        day = datetime.fromtimestamp(timestamp, timezone.utc).date().isoformat()
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            daily = connection.execute(
                "SELECT COUNT(*) FROM provider_request_quota "
                "WHERE provider=? AND utc_day=?",
                (provider, day),
            ).fetchone()[0]
            minute = connection.execute(
                "SELECT COUNT(*) FROM provider_request_quota "
                "WHERE provider=? AND reserved_at>?",
                (provider, timestamp - 60),
            ).fetchone()[0]
            if daily >= self.daily_limit or minute >= self.per_minute_limit:
                connection.execute("ROLLBACK")
                raise FreeQuotaExceeded("Configured free-provider quota is exhausted.")
            connection.execute(
                "INSERT INTO provider_request_quota(provider, reserved_at, utc_day) VALUES(?,?,?)",
                (provider, timestamp, day),
            )
            connection.execute("COMMIT")


class OpenRouterFreeAdapter:
    """OpenAI-compatible chat adapter locked to a single free model variant."""

    provider_name = "openrouter"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        quota: SQLiteRequestQuota,
        timeout_seconds: float = 45.0,
    ) -> None:
        if not api_key.strip():
            raise ValueError("OpenRouter API key is required")
        if not model.strip().endswith(":free"):
            raise ValueError("OpenRouter adapter accepts only explicit :free model IDs")
        if not 5 <= timeout_seconds <= 120:
            raise ValueError("timeout must be between 5 and 120 seconds")
        self._api_key = api_key.strip()
        self.model = model.strip()
        self.quota = quota
        self.timeout_seconds = timeout_seconds

    def generate(self, request: ModelRequest, *, model: str) -> ModelResult:
        if model != self.model:
            raise ProviderUnavailable("Requested model does not match the locked free model.")
        self.quota.reserve(self.provider_name)
        payload = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": request.prompt}],
            "max_tokens": request.max_output_tokens,
            "stream": False,
        }).encode("utf-8")
        outbound = Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://opencompany.local",
                "X-Title": "OpenCompany",
            },
            method="POST",
        )
        try:
            with urlopen(outbound, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            # Never expose response bodies or credentials in logs/errors.
            raise ProviderUnavailable(f"OpenRouter returned HTTP {exc.code}.") from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise ProviderUnavailable("OpenRouter request failed or timed out.") from None
        try:
            if not isinstance(data, dict):
                raise ValueError
            returned_model = str(data.get("model") or self.model)
            if returned_model not in {self.model, self.model.removesuffix(":free")}:
                raise ValueError
            usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
            reported_cost = usage.get("cost", data.get("cost"))
            if reported_cost is not None:
                cost = float(reported_cost)
                if cost != 0.0 or not __import__("math").isfinite(cost):
                    raise ValueError
            content = data["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(
                    part.get("text", "") for part in content if isinstance(part, dict)
                )
            if not isinstance(content, str) or not content.strip():
                raise ValueError
        except (KeyError, IndexError, TypeError, ValueError):
            raise ProviderUnavailable("OpenRouter returned an unsupported response shape.") from None
        return ModelResult(
            text=content, provider=self.provider_name, model=self.model, cost_usd=0.0,
        )


def openrouter_free_gateway_from_env(*, quota_database: str | None = None) -> ModelGateway | None:
    """Build a gateway only when the owner explicitly configures a free model."""
    api_key = os.environ.get("OPENCOMPANY_OPENROUTER_API_KEY", "").strip()
    model = os.environ.get("OPENCOMPANY_OPENROUTER_FREE_MODEL", "").strip()
    confirmation = os.environ.get("OPENCOMPANY_CONFIRM_OPENROUTER_FREE", "").strip().lower()
    if not api_key and not model and not confirmation:
        return None
    if not api_key or not model or confirmation != "true":
        raise ValueError(
            "OpenRouter activation requires an API key, an explicit :free model ID, "
            "and OPENCOMPANY_CONFIRM_OPENROUTER_FREE=true."
        )
    database = quota_database or os.environ.get(
        "OPENCOMPANY_PROVIDER_QUOTA_DATABASE", "data/opencompany_provider_quotas.sqlite3"
    )
    adapter = OpenRouterFreeAdapter(
        api_key=api_key, model=model, quota=SQLiteRequestQuota(database),
    )
    policy = ProviderPolicy(
        name=adapter.provider_name, model=model,
        billing_mode=BillingMode.FREE_CONFIRMED,
        max_cost_per_request_usd=0.0, priority=10,
    )
    return ModelGateway.configure(((policy, adapter),))
