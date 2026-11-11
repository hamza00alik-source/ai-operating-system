import json

import pytest

from fastapi.testclient import TestClient

from ai_os import llm_gateway
from ai_os.api import app


def clear_provider_env(monkeypatch):
    for name in (
        "AI_OS_GROQ_BASE_URL", "AI_OS_GROQ_MODEL", "AI_OS_GROQ_API_KEY",
        "AI_OS_GROQ_FREE_CONFIRMED",
    ):
        monkeypatch.delenv(name, raising=False)


def test_provider_is_blocked_by_default(monkeypatch):
    clear_provider_env(monkeypatch)
    provider = next(p for p in llm_gateway.list_providers() if p["id"] == "groq")
    assert provider["configured"] is False
    assert provider["eligible"] is False


def test_provider_status_never_exposes_secret(monkeypatch):
    monkeypatch.setenv("AI_OS_GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("AI_OS_GROQ_MODEL", "example-model")
    monkeypatch.setenv("AI_OS_GROQ_API_KEY", "do-not-leak-this-secret")
    monkeypatch.setenv("AI_OS_GROQ_FREE_CONFIRMED", "true")
    status = next(p for p in llm_gateway.list_providers() if p["id"] == "groq")
    assert status["eligible"] is True
    assert "do-not-leak-this-secret" not in json.dumps(status)
    assert "api_key" not in json.dumps(status).lower()


def test_gateway_executes_real_adapter_path_with_mocked_transport(monkeypatch):
    monkeypatch.setenv("AI_OS_GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("AI_OS_GROQ_MODEL", "example-model")
    monkeypatch.setenv("AI_OS_GROQ_API_KEY", "test-secret")
    monkeypatch.setenv("AI_OS_GROQ_FREE_CONFIRMED", "true")
    captured = {}

    def fake_post(url, payload, headers, timeout=35):
        captured.update(url=url, payload=payload, headers=headers)
        return {"choices": [{"message": {"content": "AIOS live connection successful"}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 4, "total_tokens": 11}}

    monkeypatch.setattr(llm_gateway, "_post", fake_post)
    result = llm_gateway.test_provider("groq")
    assert result["test_passed"] is True
    assert result["live"] is True
    assert result["usage"]["total_tokens"] == 11
    assert captured["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-secret"


def test_openrouter_free_route_uses_compatible_api_and_reports_usage(monkeypatch):
    monkeypatch.setenv("AI_OS_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("AI_OS_OPENROUTER_MODEL", "provider/model:free")
    monkeypatch.setenv("AI_OS_OPENROUTER_API_KEY", "test-openrouter-secret")
    monkeypatch.setenv("AI_OS_OPENROUTER_FREE_CONFIRMED", "true")
    captured = {}

    def fake_post(url, payload, headers, timeout=35):
        captured.update(url=url, payload=payload, headers=headers)
        return {
            "choices": [{"message": {"content": "AIOS live connection successful"}}],
            "usage": {"prompt_tokens": 13, "completion_tokens": 5, "total_tokens": 18},
        }

    monkeypatch.setattr(llm_gateway, "_post", fake_post)
    result = llm_gateway.test_provider("openrouter")
    assert result["test_passed"] is True
    assert result["provider"] == "openrouter"
    assert result["usage"]["total_tokens"] == 18
    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-openrouter-secret"
    assert captured["headers"]["X-Title"] == "AI Operating System"
    assert captured["payload"]["model"] == "provider/model:free"


def test_openrouter_is_blocked_unless_owner_confirms_free(monkeypatch):
    monkeypatch.setenv("AI_OS_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("AI_OS_OPENROUTER_MODEL", "provider/model:free")
    monkeypatch.setenv("AI_OS_OPENROUTER_API_KEY", "test-secret")
    monkeypatch.setenv("AI_OS_OPENROUTER_FREE_CONFIRMED", "false")
    status = next(p for p in llm_gateway.list_providers() if p["id"] == "openrouter")
    assert status["configured"] is True
    assert status["eligible"] is False


def test_llm_endpoint_blocks_unconfigured_provider(monkeypatch):
    clear_provider_env(monkeypatch)
    with TestClient(app) as client:
        response = client.post("/llm/test", json={"provider": "groq", "prompt": "hello"})
    assert response.status_code == 403



def test_fallback_error_identifies_each_provider_without_secrets(monkeypatch):
    def fake_config(provider):
        eligible = provider.key in {"openrouter", "groq"}
        return {"eligible": eligible, "configured": eligible, "free_confirmed": eligible}

    def fake_generate(provider_id, prompt):
        raise llm_gateway.ProviderHTTPError(403, "error code: 1010")

    monkeypatch.setattr(llm_gateway, "_provider_config", fake_config)
    monkeypatch.setattr(llm_gateway, "generate", fake_generate)

    try:
        llm_gateway.generate_with_fallback("test", preferred_provider="openrouter")
        assert False, "Expected all providers to fail"
    except RuntimeError as exc:
        message = str(exc)
        assert "openrouter: unavailable (HTTP 403)" in message
        assert "groq: unavailable (HTTP 403)" in message
        assert "No paid fallback was attempted" in message
        assert "secret" not in message.lower()


def test_unorouter_is_eligible_for_prelaunch_aios_when_free_confirmed(monkeypatch):
    monkeypatch.setenv("AI_OS_UNOROUTER_BASE_URL", "https://api.unorouter.com/v1")
    monkeypatch.setenv("AI_OS_UNOROUTER_MODEL", "example-model:free")
    monkeypatch.setenv("AI_OS_UNOROUTER_API_KEY", "unorouter-test-secret")
    monkeypatch.setenv("AI_OS_UNOROUTER_FREE_CONFIRMED", "true")
    status = next(p for p in llm_gateway.list_providers() if p["id"] == "unorouter")
    assert status["eligible"] is True
    assert status["model"] == "example-model:free"
    assert "unorouter-test-secret" not in json.dumps(llm_gateway.list_providers())


def test_unorouter_discovery_only_key_is_eligible_when_free_only_confirmed(monkeypatch):
    monkeypatch.setattr(llm_gateway, "get_provider_credential", lambda provider: {
        "secret": "uno-discovery-key", "model": "__catalog_only__",
        "base_url": "https://api.unorouter.com/v1", "free_confirmed": True
    } if provider == "unorouter" else None)
    status = next(p for p in llm_gateway.list_providers() if p["id"] == "unorouter")
    assert status["configured"] is True
    assert status["free_confirmed"] is True
    assert status["eligible"] is True
    assert status["model"] == "__catalog_only__"
    assert "uno-discovery-key" not in json.dumps(status)


def test_unorouter_discovery_only_key_is_blocked_without_free_confirmation(monkeypatch):
    monkeypatch.setattr(llm_gateway, "get_provider_credential", lambda provider: {
        "secret": "uno-discovery-key", "model": "__catalog_only__",
        "base_url": "https://api.unorouter.com/v1", "free_confirmed": False
    } if provider == "unorouter" else None)
    status = next(p for p in llm_gateway.list_providers() if p["id"] == "unorouter")
    assert status["configured"] is True
    assert status["eligible"] is False


def test_unorouter_catalog_lists_free_and_paid_and_preserves_exact_ids(monkeypatch):
    monkeypatch.setattr(llm_gateway, "get_provider_credential", lambda provider: {
        "secret": "catalog-key", "model": "gpt-oss-120b:free",
        "base_url": "https://api.unorouter.com/v1", "free_confirmed": True
    } if provider == "unorouter" else None)
    responses = [
        {"counts":{"models":2,"free":1,"paid":1},"models":[
            {"model_name":"gpt-oss-120b","vendor":"Vendor A","is_free":True,"online":True,"input_price":0,"output_price":0},
            {"model_name":"paid-model","vendor":"Vendor B","is_free":False,"online":True,"input_price":1.2,"output_price":4.8}
        ]},
        {"data":[{"id":"gpt-oss-120b:free","name":"GPT OSS"},{"id":"paid-model","name":"Paid Model"}]}
    ]
    class FakeResponse:
        def __init__(self,payload): self.payload=payload
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def read(self,limit): return json.dumps(self.payload).encode()
    calls=[]
    def fake_urlopen(request,timeout=20):
        calls.append(request.full_url)
        return FakeResponse(responses.pop(0))
    monkeypatch.setattr(llm_gateway.urllib.request,"urlopen",fake_urlopen)
    data=llm_gateway.list_unorouter_catalog()
    assert data["available_to_key_count"]==2
    assert data["available_free_count"]==1
    assert data["available_paid_count"]==1
    assert {m["id"] for m in data["models"]}=={"gpt-oss-120b:free","paid-model"}
    assert next(m for m in data["models"] if m["id"]=="paid-model")["input_price_per_million"]==1.2
    assert calls==["https://api.unorouter.com/api/pricing/catalog","https://api.unorouter.com/v1/models"]



def test_unorouter_is_default_eligible_provider_when_free_confirmed(monkeypatch):
    monkeypatch.setenv("AI_OS_UNOROUTER_BASE_URL", "https://api.unorouter.com/v1")
    monkeypatch.setenv("AI_OS_UNOROUTER_MODEL", "example-model:free")
    monkeypatch.setenv("AI_OS_UNOROUTER_API_KEY", "test-secret")
    monkeypatch.setenv("AI_OS_UNOROUTER_FREE_CONFIRMED", "true")
    status = next(p for p in llm_gateway.list_providers() if p["id"] == "unorouter")
    assert status["configured"] is True
    assert status["free_confirmed"] is True
    assert status["eligible"] is True
    assert status["experimental_only"] is False
    assert llm_gateway.generate_with_fallback.__defaults__[0] == "unorouter"


def test_unorouter_personal_test_is_separate_and_never_company_eligible(monkeypatch):
    monkeypatch.setattr(llm_gateway, "get_provider_credential", lambda provider: {
        "secret": "uno-test-secret", "model": "sample-model:free",
        "base_url": "https://api.unorouter.com/v1", "free_confirmed": True
    } if provider == "unorouter" else None)
    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, limit):
            return json.dumps({"model":"sample-model:free","choices":[{"message":{"content":"This is a valid personal test response."}}],"usage":{"prompt_tokens":5,"completion_tokens":8,"total_tokens":13}}).encode()
    monkeypatch.setattr(llm_gateway.urllib.request, "urlopen", lambda *a, **k: FakeResponse())
    result = llm_gateway.test_unorouter_personal("Explain a harmless programming concept.")
    assert result["mode"] == "owner_personal_test_only"
    assert result["company_task_routing"] is False
    assert result["response"].startswith("This is a valid")
    assert next(p for p in llm_gateway.list_providers() if p["id"] == "unorouter")["eligible"] is True

def test_unorouter_personal_test_rejects_paid_model(monkeypatch):
    monkeypatch.setattr(llm_gateway, "get_provider_credential", lambda provider: {
        "secret": "uno-test-secret", "model": "paid-model",
        "base_url": "https://api.unorouter.com/v1", "free_confirmed": True
    })
    with pytest.raises(PermissionError):
        llm_gateway.test_unorouter_personal("test")


def test_unorouter_env_model_must_end_in_free(monkeypatch):
    monkeypatch.setenv("AI_OS_UNOROUTER_BASE_URL", "https://api.unorouter.com/v1")
    monkeypatch.setenv("AI_OS_UNOROUTER_MODEL", "paid-model")
    monkeypatch.setenv("AI_OS_UNOROUTER_API_KEY", "test-secret")
    monkeypatch.setenv("AI_OS_UNOROUTER_FREE_CONFIRMED", "true")
    status = next(p for p in llm_gateway.list_providers() if p["id"] == "unorouter")
    assert status["configured"] is True
    assert status["eligible"] is False
    assert ":free" in status["reason"]


def test_unorouter_paid_personal_test_requires_explicit_approval(monkeypatch):
    monkeypatch.setattr(llm_gateway, "get_provider_credential", lambda provider: {
        "secret": "uno-test-secret", "model": "paid-model",
        "base_url": "https://api.unorouter.com/v1", "free_confirmed": False
    } if provider == "unorouter" else None)
    with pytest.raises(PermissionError, match="Explicitly approve"):
        llm_gateway.test_unorouter_personal("test prompt", approve_paid_request=False)


def test_unorouter_paid_personal_test_runs_only_when_approved(monkeypatch):
    monkeypatch.setattr(llm_gateway, "get_provider_credential", lambda provider: {
        "secret": "uno-test-secret", "model": "paid-model",
        "base_url": "https://api.unorouter.com/v1", "free_confirmed": False
    } if provider == "unorouter" else None)
    captured={}
    def fake_post(url,payload,headers,timeout=35):
        captured.update(url=url,payload=payload)
        return {"model":"paid-model","choices":[{"message":{"content":"Approved paid model test returned a valid response."}}],"usage":{}}
    monkeypatch.setattr(llm_gateway,"_post",fake_post)
    result=llm_gateway.test_unorouter_personal("test prompt",approve_paid_request=True)
    assert result["model_cost_class"]=="paid"
    assert result["paid_request_approved"] is True
    assert captured["payload"]["model"]=="paid-model"



def test_unorouter_task_router_selects_free_chat_model_for_coding(monkeypatch):
    monkeypatch.setattr(llm_gateway, "get_provider_credential", lambda provider: {
        "secret": "uno-router-test-key", "model": "albedobase-xl-sdxl:free",
        "base_url": "https://api.unorouter.com/v1", "free_confirmed": True
    } if provider == "unorouter" else None)
    monkeypatch.setattr(llm_gateway, "_UNO_CATALOG_CACHE", {
        "fingerprint": None, "expires_at": 0.0, "catalog": None
    })
    monkeypatch.setattr(llm_gateway, "list_unorouter_catalog", lambda: {
        "models": [
            {"id": "albedobase-xl-sdxl:free", "free": True, "callable": True,
             "online": True, "supported_endpoint_types": ["images"]},
            {"id": "qwen-coder:free", "free": True, "callable": True,
             "online": True, "vendor": "Qwen", "context_length": 32000,
             "supported_endpoint_types": ["chat.completions"]},
            {"id": "gpt-oss-chat:free", "free": True, "callable": True,
             "online": True, "context_length": 64000,
             "supported_endpoint_types": ["chat.completions"]},
            {"id": "paid-coder", "free": False, "callable": True,
             "online": True, "supported_endpoint_types": ["chat.completions"]},
        ]
    })
    selected = llm_gateway.select_unorouter_model("Implement a Python API endpoint")
    assert selected["task_category"] == "coding"
    assert selected["model_id"] == "qwen-coder:free"
    assert selected["candidate_count"] == 2
    assert selected["benchmark_status"].startswith("not benchmarked")



def test_unorouter_skips_consent_required_free_model_and_retries_another_free_model(monkeypatch):
    provider = next(p for p in llm_gateway.PROVIDERS if p.key == "unorouter")
    monkeypatch.setattr(llm_gateway, "_resolve", lambda provider_id: (
        provider, {"base_url": "https://api.unorouter.com/v1",
                   "_secret": "uno-test-secret", "model": "__catalog_only__"}
    ))
    selections = [
        {"task_category": "reasoning", "model_id": "first-model:free"},
        {"task_category": "reasoning", "model_id": "second-model:free"},
    ]
    excluded = []
    def select(prompt, exclude_model_ids=None):
        excluded.append(set(exclude_model_ids or set()))
        return selections.pop(0)
    monkeypatch.setattr(llm_gateway, "select_unorouter_model", select)
    calls = []
    def fake_post(url, payload, headers, timeout=35):
        calls.append(payload["model"])
        if len(calls) == 1:
            raise llm_gateway.ProviderHTTPError(403, '{"error":{"code":"consent_required"}}')
        return {"model": payload["model"],
                "choices": [{"message": {"content": "A valid free-model response with enough detail."}}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 8}}
    monkeypatch.setattr(llm_gateway, "_post", fake_post)
    result = llm_gateway.generate("unorouter", "Reason through this problem")
    assert calls == ["first-model:free", "second-model:free"]
    assert result["model"] == "second-model:free"
    assert result["model_selection"]["consent_skipped_model_ids"] == ["first-model:free"]
    assert excluded == [set(), {"first-model:free"}]


def test_unorouter_auto_selection_uses_selected_free_chat_model_without_paid_requests(monkeypatch):
    provider = next(p for p in llm_gateway.PROVIDERS if p.key == "unorouter")
    monkeypatch.setattr(llm_gateway, "_resolve", lambda provider_id: (
        provider, {"base_url": "https://api.unorouter.com/v1",
                   "_secret": "uno-test-secret", "model": "default:free"}
    ))
    selection = {
        "task_category": "research", "model_id": "research-chat:free",
        "strategy": "account-accessible free chat models; metadata/name heuristic",
        "candidate_count": 3, "benchmark_status": "not benchmarked; no extra inference calls made",
    }
    monkeypatch.setattr(llm_gateway, "select_unorouter_model", lambda prompt: selection)
    captured = {}
    def fake_post(url, payload, headers, timeout=35):
        captured.update(url=url, payload=payload, headers=headers)
        return {"model": "research-chat:free",
                "choices": [{"message": {"content": "This is a sufficiently detailed response from the selected free chat model."}}],
                "usage": {"prompt_tokens": 8, "completion_tokens": 12}}
    monkeypatch.setattr(llm_gateway, "_post", fake_post)
    result = llm_gateway.generate("unorouter", "Research current market evidence")
    assert captured["payload"]["model"] == "research-chat:free"
    assert result["model_selection"]["task_category"] == "research"
    assert result["model_selection"]["model_id"].endswith(":free")
