import pytest
from ai_os.discovery import create_scan, evaluate_repository, list_scans
from ai_os.db import initialize_database

def test_evaluation_keeps_unknown_cost_and_commercial_terms_unknown():
    result = evaluate_repository({
        "full_name": "example/project", "html_url": "https://github.com/example/project",
        "description": "Example", "archived": False,
        "license": {"spdx_id": "MIT"}, "pushed_at": "2026-10-01T00:00:00Z",
        "stargazers_count": 42,
    }, "agent-frameworks")
    assert result["license"] == "MIT"
    assert result["status"] == "discovered"
    assert result["evidence"]["cost"] == "unknown"
    assert result["evidence"]["commercial_use"] == "not-verified"
    assert result["evidence"]["security"] == "not-tested"

def test_archived_or_unlicensed_projects_need_review():
    archived = evaluate_repository({"html_url":"https://github.com/a/b","archived":True}, "mcp-servers")
    unlicensed = evaluate_repository({"html_url":"https://github.com/c/d","archived":False}, "mcp-servers")
    assert archived["status"] == "needs-review"
    assert unlicensed["status"] == "needs-review"

def test_scan_rejects_unknown_categories():
    initialize_database()
    with pytest.raises(ValueError):
        create_scan(["made-up-category"])


def test_free_api_catalog_sync_imports_evidence_without_enabling_providers(monkeypatch):
    from ai_os import discovery
    from ai_os.db import connect

    catalog = {
        "meta": {"last_full_review": "2026-09-26"},
        "providers": [{
            "id": "sample-provider", "name": "Sample Provider",
            "category": "text_llm", "website": "https://example.com",
            "api_key_url": "https://example.com/key",
            "base_url": "https://api.example.com/v1",
            "free_tier": {"headline": "Limited free tier"},
            "policy": {"trains_on_your_data": "no", "commercial_use": "unclear"},
            "confidence": "partial", "last_verified": "2026-09-26",
            "probe": {"docs_url": "https://example.com/docs"},
        }],
    }
    status = {
        "summary": {"checked_at": "2026-11-08T11:21:23Z", "providers": 1, "live_up": 1},
        "results": {"sample-provider": {"live": {"state": "up"}}},
    }
    monkeypatch.setattr(
        discovery, "_fetch_catalog_json",
        lambda url: catalog if url.endswith("providers.json") else status,
    )
    result = discovery.sync_free_api_catalog()
    assert result["imported"] == 1
    listed = discovery.list_free_api_catalog()
    assert listed["provider_count"] == 1
    provider = listed["providers"][0]
    assert provider["name"] == "Sample Provider"
    assert provider["policy"]["commercial_use"] == "unclear"
    assert provider["status"]["live"]["state"] == "up"
    assert provider["review_state"] == "pending"
    assert "no provider was enabled" in result["important"].lower()
