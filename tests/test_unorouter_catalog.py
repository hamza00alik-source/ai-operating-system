import json
import pytest

from opencompany_core import unorouter_adapter
from opencompany_core.model_gateway import (
    BillingMode, ModelGateway, ModelRequest, ModelResult, NoEligibleProvider, ProviderPolicy, ProviderUnavailable,
)


def test_discovery_intersects_free_online_catalogue_with_key_access(monkeypatch):
    responses = iter([
        {"models": [
            {"model_name": "alpha:free", "type": "text", "chat": True, "supported_endpoint_types": ["openai"], "is_free": True, "input_price": 0, "output_price": 0, "fixed_price": 0, "online": True},
            {"model_name": "paid", "type": "text", "supported_endpoint_types": ["openai"], "is_free": False, "online": True},
            {"model_name": "offline:free", "type": "text", "chat": True, "supported_endpoint_types": ["openai"], "is_free": True, "input_price": 0, "output_price": 0, "fixed_price": 0, "online": False},
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
        {"models": [{"model_name": "paid", "type": "text", "supported_endpoint_types": ["openai"], "is_free": False, "online": True}]},
        {"data": [{"id": "paid"}]},
    ])
    monkeypatch.setattr(unorouter_adapter, "_read_json", lambda *a, **k: next(responses))
    monkeypatch.setattr(unorouter_adapter, "_catalog_cache", {})
    with pytest.raises(unorouter_adapter.ProviderUnavailable, match="No models were confirmed free"):
        unorouter_adapter.discover_free_models("test-api-key", force_refresh=True)


def test_discovery_excludes_non_chat_and_non_openai_models(monkeypatch):
    responses = iter([
        {"models": [
            {"model_name": "chat:free", "type": "text", "chat": True, "supported_endpoint_types": ["openai"], "is_free": True, "input_price": 0, "output_price": 0, "fixed_price": 0, "online": True},
            {"model_name": "image:free", "type": "image", "chat": False, "supported_endpoint_types": ["openai"], "is_free": True, "input_price": 0, "output_price": 0, "fixed_price": 0, "online": True},
            {"model_name": "embedding:free", "type": "embedding", "chat": False, "supported_endpoint_types": ["openai"], "is_free": True, "input_price": 0, "output_price": 0, "fixed_price": 0, "online": True},
            {"model_name": "anthropic-only:free", "type": "text", "chat": True, "supported_endpoint_types": ["anthropic"], "is_free": True, "input_price": 0, "output_price": 0, "fixed_price": 0, "online": True},
        ]},
        {"data": [
            {"id": "chat:free"}, {"id": "image:free"},
            {"id": "embedding:free"}, {"id": "anthropic-only:free"},
        ]},
    ])
    monkeypatch.setattr(unorouter_adapter, "_read_json", lambda *a, **k: next(responses))
    monkeypatch.setattr(unorouter_adapter, "_catalog_cache", {})
    assert unorouter_adapter.discover_free_models("test-api-key", force_refresh=True) == ("chat:free",)


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


def test_auto_catalog_adapter_skips_unavailable_free_model(monkeypatch):
    seen = []
    monkeypatch.setattr(unorouter_adapter, "discover_free_models", lambda *a, **k: ("alpha:free", "beta:free"))
    monkeypatch.setattr(unorouter_adapter, "_round_robin_index", 0)

    def generate_one(self, request, *, model):
        seen.append(model)
        if model == "alpha:free":
            raise ProviderUnavailable("UnoRouter returned HTTP 503.")
        return ModelResult("ok", "unorouter", model, 0.0, 1, 1)

    monkeypatch.setattr(unorouter_adapter.UnoRouterAdapter, "_generate_one", generate_one)
    adapter = unorouter_adapter.UnoRouterAdapter("test-api-key")
    result = adapter.generate(ModelRequest("test", "req-fallback"), model=unorouter_adapter.UNOROUTER_AUTO_FREE_MODEL)
    assert result.model == "beta:free"
    assert seen == ["alpha:free", "beta:free"]



def test_free_chat_response_without_cost_field_is_rejected(monkeypatch):
    payload = {
        "model": "alpha",
        "choices": [{"message": {"content": "OPENCOMPANY_UNOROUTER_OK"}}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2},
    }

    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, limit): return json.dumps(payload).encode("utf-8")

    monkeypatch.setattr(unorouter_adapter, "urlopen", lambda *a, **k: Response())
    adapter = unorouter_adapter.UnoRouterAdapter("test-api-key")
    with pytest.raises(ProviderUnavailable, match="omitted transaction cost"):
        adapter._generate_one(ModelRequest("test", "req-no-cost-field"), model="alpha:free")

def test_auto_catalog_adapter_reaches_models_beyond_old_attempt_limit(monkeypatch):
    models = tuple(f"model-{index}:free" for index in range(7))
    seen = []
    monkeypatch.setattr(unorouter_adapter, "discover_free_models", lambda *a, **k: models)
    monkeypatch.setattr(unorouter_adapter, "_round_robin_index", 0)

    def generate_one(self, request, *, model):
        seen.append(model)
        if model != models[-1]:
            raise ProviderUnavailable("UnoRouter returned HTTP 503.")
        return ModelResult("ok", "unorouter", model, 0.0, 1, 1)

    monkeypatch.setattr(unorouter_adapter.UnoRouterAdapter, "_generate_one", generate_one)
    adapter = unorouter_adapter.UnoRouterAdapter("test-api-key")
    result = adapter.generate(
        ModelRequest("test", "req-all-free-models"),
        model=unorouter_adapter.UNOROUTER_AUTO_FREE_MODEL,
    )
    assert result.model == models[-1]
    assert seen == list(models)


def test_full_catalog_import_marks_paid_and_unsupported_models_blocked(monkeypatch):
    responses = iter([
        {"models": [
            {"model_name":"free-chat:free","vendor":"A","type":"text","chat":True,"is_free":True,"online":True,"input_price":0,"output_price":0,"fixed_price":0,"supported_endpoint_types":["openai"]},
            {"model_name":"paid-chat","vendor":"B","type":"text","chat":True,"is_free":False,"online":True,"input_price":1,"output_price":2,"fixed_price":0,"supported_endpoint_types":["openai"]},
            {"model_name":"free-image:free","vendor":"C","type":"image","chat":False,"is_free":True,"online":True,"input_price":0,"output_price":0,"fixed_price":0,"supported_endpoint_types":["openai"]},
        ]},
        {"data":[{"id":"free-chat:free"},{"id":"paid-chat"},{"id":"free-image:free"}]},
    ])
    monkeypatch.setattr(unorouter_adapter,"_read_json",lambda *a,**k:next(responses))
    catalog=unorouter_adapter.discover_model_catalog("test-api-key")
    assert len(catalog)==3
    assert [x["model_id"] for x in catalog if x["allowed_for_inference"]]==["free-chat:free"]
    assert next(x for x in catalog if x["model_id"]=="paid-chat")["policy_status"]=="paid_or_unverified_pricing"
    assert next(x for x in catalog if x["model_id"]=="free-image:free")["policy_status"]=="unsupported_for_chat_inference"


def test_free_discovery_requires_explicit_zero_price_and_free_flag(monkeypatch):
    responses=iter([
        {"models":[
            {"model_name":"false-free:free","type":"text","chat":True,"is_free":False,"online":True,"input_price":0,"output_price":0,"fixed_price":0,"supported_endpoint_types":["openai"]},
            {"model_name":"real-free:free","type":"text","chat":True,"is_free":True,"online":True,"input_price":0,"output_price":0,"fixed_price":0,"supported_endpoint_types":["openai"]},
        ]},
        {"data":[{"id":"false-free:free"},{"id":"real-free:free"}]},
    ])
    monkeypatch.setattr(unorouter_adapter,"_read_json",lambda *a,**k:next(responses))
    monkeypatch.setattr(unorouter_adapter,"_catalog_cache",{})
    assert unorouter_adapter.discover_free_models("test-api-key",force_refresh=True)==("real-free:free",)


def test_gateway_globally_blocks_paid_provider_even_with_positive_budget():
    class PaidAdapter:
        def generate(self, request, *, model):
            raise AssertionError("paid adapter must never be invoked")
    gateway = ModelGateway.configure(((
        ProviderPolicy(
            name="paid-provider", model="paid-model",
            billing_mode=BillingMode.PAID_OWNER_APPROVED,
            max_cost_per_request_usd=10.0,
        ),
        PaidAdapter(),
    ),))
    assert gateway.eligible_providers(request_budget_usd=100.0) == ()
    with pytest.raises(NoEligibleProvider):
        gateway.complete(ModelRequest("test", "paid-block-test"), request_budget_usd=100.0)
