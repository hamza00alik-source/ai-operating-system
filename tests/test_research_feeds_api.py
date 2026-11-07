from fastapi.testclient import TestClient

import ai_os.api as api
from ai_os.api import app


def test_free_feed_endpoint_saves_unreviewed_candidates_and_deduplicates(monkeypatch):
    monkeypatch.setattr(api, "collect_release_feed_candidates", lambda query, max_per_feed=5: [{
        "url": "https://github.com/langchain-ai/langgraph/releases/tag/v-test",
        "title": "LangGraph agent orchestration update",
        "published_date": "2026-11-01T00:00:00+00:00",
        "excerpt": "Release notes about agent orchestration.",
        "source_title": "LangGraph releases",
        "match_terms": 2,
    }])
    payload = {"query": "agent orchestration improvements", "tags": ["agents"]}
    with TestClient(app) as client:
        first = client.post("/research/feeds", json=payload)
        second = client.post("/research/feeds", json=payload)
        listed = client.get("/knowledge", params={"status": "candidate"})
    assert first.status_code == 200, first.text
    assert first.json()["candidates_created"] == 1
    assert first.json()["provider"] == "github_release_feeds"
    assert first.json()["items"][0]["status"] == "candidate"
    assert second.status_code == 200, second.text
    assert second.json()["candidates_created"] == 0
    assert second.json()["duplicates_skipped"] == 1
    assert sum(item["source_url"].endswith("/v-test") for item in listed.json()) == 1


def test_free_feed_endpoint_rejects_blank_query():
    with TestClient(app) as client:
        response = client.post("/research/feeds", json={"query": "  "})
    assert response.status_code == 422
