import json

import pytest
from fastapi.testclient import TestClient

from ai_os.api import app


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("AI_OS_ENV", "development")
    monkeypatch.setenv("AI_OS_LLM_PROVIDERS", json.dumps([{
        "name": "test-provider",
        "base_url": "https://api.example.test/v1",
        "model": "test-model",
        "api_key_env": "TEST_LLM_KEY",
        "free_tier_confirmed": True,
    }]))
    monkeypatch.setenv("TEST_LLM_KEY", "test-secret")
    with TestClient(app) as test_client:
        yield test_client


def test_provider_status_never_exposes_secret(client):
    response = client.get("/llm/providers")
    assert response.status_code == 200
    body = response.json()
    assert body[0]["name"] == "test-provider"
    assert body[0]["configured"] is True
    assert "test-secret" not in response.text


def test_llm_test_rejects_unknown_provider(client):
    response = client.post("/llm/test", json={"provider": "missing", "prompt": "hello"})
    assert response.status_code == 404


def test_llm_test_blocks_unconfirmed_paid_provider(client, monkeypatch):
    monkeypatch.setenv("AI_OS_LLM_PROVIDERS", json.dumps([{
        "name": "test-provider",
        "base_url": "https://api.example.test/v1",
        "model": "test-model",
        "api_key_env": "TEST_LLM_KEY",
    }]))
    response = client.post("/llm/test", json={"provider": "test-provider", "prompt": "hello"})
    assert response.status_code == 403


def test_llm_test_returns_completion_from_provider(client, monkeypatch):
    from ai_os import llm

    class FakeResponse:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {
                "choices": [{"message": {"content": "AIOS connection test passed."}}],
                "usage": {"prompt_tokens": 8, "completion_tokens": 6, "total_tokens": 14},
            }

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, headers, json):
            assert url == "https://api.example.test/v1/chat/completions"
            assert headers["Authorization"] == "Bearer test-secret"
            assert json["model"] == "test-model"
            return FakeResponse()

    monkeypatch.setattr(llm.httpx, "AsyncClient", FakeAsyncClient)
    response = client.post(
        "/llm/test",
        json={"provider": "test-provider", "prompt": "Say the test passed."},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["response"] == "AIOS connection test passed."
    assert response.json()["usage"]["total_tokens"] == 14
