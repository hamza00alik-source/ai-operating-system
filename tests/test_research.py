import json

from fastapi.testclient import TestClient

from ai_os.api import app
from ai_os import research


def test_research_disabled_by_default_makes_no_provider_call(monkeypatch):
    monkeypatch.delenv("AI_OS_RESEARCH_ENABLED", raising=False)
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    with TestClient(app) as client:
        status = client.get("/research/status")
        response = client.post("/research/search", json={"query": "recent game asset demand"})
    assert status.status_code == 200
    assert status.json()["enabled"] is False
    assert response.status_code == 503


def test_research_search_creates_only_candidate_knowledge(monkeypatch):
    monkeypatch.setenv("AI_OS_RESEARCH_ENABLED", "true")
    monkeypatch.setenv("EXA_API_KEY", "test-secret-key")
    monkeypatch.setattr(research, "search_exa", lambda query, num_results=5: [{
        "url": "https://example.com/report",
        "title": "Buyer demand report",
        "published_date": "2026-10-20",
        "excerpt": "Evidence excerpt about buyer demand.",
    }])
    with TestClient(app) as client:
        response = client.post("/research/search", json={
            "query": "downloadable gaming product demand",
            "tags": ["gaming", "digital-products"],
        })
        candidates = client.get("/knowledge", params={"status": "candidate"})
    assert response.status_code == 200, response.text
    assert len(response.json()["items"]) == 1
    item = response.json()["items"][0]
    assert item["status"] == "candidate"
    assert item["source_url"] == "https://example.com/report"
    assert item["source_published_at"].startswith("2026-10-20")
    assert any(row["id"] == item["id"] for row in candidates.json())


def test_research_provider_errors_are_sanitized(monkeypatch):
    monkeypatch.setenv("AI_OS_RESEARCH_ENABLED", "true")
    monkeypatch.setenv("EXA_API_KEY", "test-secret-key")
    def fail(*args, **kwargs):
        raise research.ResearchProviderError("Research provider could not be reached.")
    monkeypatch.setattr(research, "search_exa", fail)
    with TestClient(app) as client:
        response = client.post("/research/search", json={"query": "recent game asset demand"})
    assert response.status_code == 502
    assert "test-secret-key" not in response.text


def test_exa_response_normalization_skips_untrusted_or_empty_results(monkeypatch):
    monkeypatch.setenv("AI_OS_RESEARCH_ENABLED", "true")
    monkeypatch.setenv("EXA_API_KEY", "test-secret-key")
    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, size):
            return json.dumps({"results": [
                {"url": "javascript:alert(1)", "title": "bad", "highlights": ["x"]},
                {"url": "https://example.com/empty", "title": "empty", "highlights": []},
                {"url": "https://example.com/good", "title": "Good", "highlights": ["Useful excerpt"]},
            ]}).encode()
    monkeypatch.setattr(research, "urlopen", lambda *args, **kwargs: FakeResponse())
    results = research.search_exa("game asset demand")
    assert len(results) == 1
    assert results[0]["url"] == "https://example.com/good"
