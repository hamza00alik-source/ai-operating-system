import pytest

from opencompany_core import unorouter_adapter
from opencompany_core.model_gateway import (
    BillingMode, ModelGateway, ModelRequest, ModelResult, ProviderPolicy,
)


def test_discovery_intersects_free_online_catalogue_with_key_access(monkeypatch):
    responses = iter([
        {"models": [
            {"model_name": "alpha", "is_free": False, "online": True},
            {"model_name": "paid", "is_free": False, "online": True},
            {"model_name": "offline", "is_free": True, "online": False},
        ]},
        {"data": [
            {"id": "alpha:free"},
            {"id": "paid"},
            {"id": "not-in-catalogue:free"},
        ]},
    ])
    monkeypatch.setattr(unorouter_adapter, "_read_json", lambda *a, **k: next(responses))
    monkeypatch.setattr(unorouter_adapter, "_catalog_cache", {})
    assert unorouter_adapter.discover_free_models("test-api-key", force_refresh=True) == ("alpha:free",)


def test_catalogue_discovery_fails_closed_when_no_free_models_are_accessible(monkeypatch):
    responses = iter([
        {"models": [{"model_name": "paid", "is_free": False, "online": True}]},
        {"data": [{"id": "paid"}]},
    ])
    monkeypatch.setattr(unorouter_adapter, "_read_json", lambda *a, **k: next(responses))
    monkeypatch.setattr(unorouter_adapter, "_catalog_cache", {})
    with pytest.raises(unorouter_adapter.ProviderUnavailable, match="No models were confirmed free"):
        unorouter_adapter.discover_free_models("test-api-key", force_refresh=True)


def test_auto_catalog_adapter_rotates_between_free_models(monkeypatch):
    seen = []
    monkeypatch.setattr(unorouter_adapter, "discover_free_models", lambda *a, **k: ("alpha:free", "beta:free"))
    monkeypatch.setattr(unorouter_adapter, "_round_robin_index", 0)

    def generate_one(self, request, *, model):
        seen.append(model)
        return ModelResult("ok", "unorouter", model, 0.0, 1, 1)

    monkeypatch.setattr(unorouter_adapter.UnoRouterAdapter, "_generate_one", generate_one)
    adapter = unorouter_adapter.UnoRouterAdapter("test-api-key")
    adapter.generate(ModelRequest("test", "req-a"), model=unorouter_adapter.UNOROUTER_AUTO_FREE_MODEL)
    adapter.generate(ModelRequest("test", "req-b"), model=unorouter_adapter.UNOROUTER_AUTO_FREE_MODEL)
    assert seen == ["alpha:free", "beta:free"]


def test_gateway_accepts_only_free_dynamic_model_identity():
    class DynamicAdapter:
        def generate(self, request, *, model):
            return ModelResult("ok", "unorouter", "alpha:free", 0.0, 1, 1)

    gateway = ModelGateway.configure(((
        ProviderPolicy(
            name="unorouter",
            model=unorouter_adapter.UNOROUTER_AUTO_FREE_MODEL,
            billing_mode=BillingMode.FREE_CONFIRMED,
            max_cost_per_request_usd=0.0,
        ),
        DynamicAdapter(),
    ),))
    result = gateway.complete(ModelRequest("test", "req-dynamic"))
    assert result.model == "alpha:free"
    assert result.cost_usd == 0.0


def test_catalogue_auth_error_explains_inference_key_requirement(monkeypatch):
    from urllib.error import HTTPError
    import io

    def reject(*args, **kwargs):
        raise HTTPError("https://api.unorouter.com/v1/models", 401, "unauthorized", {}, io.BytesIO(b"private"))

    monkeypatch.setattr(unorouter_adapter, "urlopen", reject)
    with pytest.raises(unorouter_adapter.ProviderUnavailable, match="inference API key"):
        unorouter_adapter._read_json("https://api.unorouter.com/v1/models", api_key="wrong-token")
