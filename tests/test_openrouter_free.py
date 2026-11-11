import json
from io import BytesIO

import pytest

from opencompany_core.openrouter_free import (
    FreeQuotaExceeded, OpenRouterFreeAdapter, SQLiteRequestQuota,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        return self.payload


def test_openrouter_adapter_only_accepts_explicit_free_model():
    with pytest.raises(ValueError, match=":free"):
        OpenRouterFreeAdapter(api_key="test", model="paid/model", quota=SQLiteRequestQuota(":memory:"))


def test_sqlite_quota_reserves_and_blocks_daily_limit(tmp_path):
    quota = SQLiteRequestQuota(str(tmp_path / "quota.sqlite3"), daily_limit=2, per_minute_limit=2)
    quota.reserve("openrouter", now=1_800_000_000)
    quota.reserve("openrouter", now=1_800_000_001)
    with pytest.raises(FreeQuotaExceeded):
        quota.reserve("openrouter", now=1_800_000_002)


def test_adapter_parses_chat_response_and_reports_zero_cost(monkeypatch, tmp_path):
    import opencompany_core.openrouter_free as module
    monkeypatch.setattr(module, "urlopen", lambda *args, **kwargs: FakeResponse({
        "choices": [{"message": {"content": "A safe draft"}}]
    }))
    adapter = OpenRouterFreeAdapter(
        api_key="test-secret", model="vendor/model:free",
        quota=SQLiteRequestQuota(str(tmp_path / "quota.sqlite3")),
    )
    from opencompany_core.model_gateway import ModelRequest
    result = adapter.generate(ModelRequest("Write a draft", "request-1"), model="vendor/model:free")
    assert result.text == "A safe draft"
    assert result.cost_usd == 0.0
    assert result.provider == "openrouter"


def test_adapter_rejects_model_substitution(monkeypatch, tmp_path):
    adapter = OpenRouterFreeAdapter(
        api_key="test-secret", model="vendor/model:free",
        quota=SQLiteRequestQuota(str(tmp_path / "quota.sqlite3")),
    )
    from opencompany_core.model_gateway import ModelRequest
    from opencompany_core.model_gateway import ProviderUnavailable
    with pytest.raises(ProviderUnavailable, match="locked free model"):
        adapter.generate(ModelRequest("Do work", "request-2"), model="another/model:free")


def test_adapter_rejects_upstream_paid_model_substitution(monkeypatch, tmp_path):
    import opencompany_core.openrouter_free as module
    from opencompany_core.model_gateway import ModelRequest, ProviderUnavailable
    monkeypatch.setattr(module, "urlopen", lambda *args, **kwargs: FakeResponse({
        "model": "vendor/paid-model",
        "choices": [{"message": {"content": "A response from an unexpected model"}}],
    }))
    adapter = OpenRouterFreeAdapter(
        api_key="test-secret", model="vendor/model:free",
        quota=SQLiteRequestQuota(str(tmp_path / "substitution.sqlite3")),
    )
    with pytest.raises(ProviderUnavailable, match="different model"):
        adapter.generate(ModelRequest("Do work", "request-substitution"), model="vendor/model:free")


def test_adapter_rejects_nonzero_reported_cost(monkeypatch, tmp_path):
    import opencompany_core.openrouter_free as module
    from opencompany_core.model_gateway import ModelRequest, ProviderUnavailable
    monkeypatch.setattr(module, "urlopen", lambda *args, **kwargs: FakeResponse({
        "model": "vendor/model",
        "usage": {"cost": 0.01},
        "choices": [{"message": {"content": "This response unexpectedly cost money"}}],
    }))
    adapter = OpenRouterFreeAdapter(
        api_key="test-secret", model="vendor/model:free",
        quota=SQLiteRequestQuota(str(tmp_path / "cost.sqlite3")),
    )
    with pytest.raises(ProviderUnavailable, match="non-zero or invalid cost"):
        adapter.generate(ModelRequest("Do work", "request-cost"), model="vendor/model:free")
