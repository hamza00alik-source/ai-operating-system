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
