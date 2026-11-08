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


def test_discovery_scan_claim_is_exclusive_and_expired_lease_recovers(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'queue.db'}")
    initialize_database()
    scan = create_scan(["agent-frameworks"])

    from ai_os.discovery import _claim_scan
    first = _claim_scan(worker_id="worker-a")
    assert first is not None
    assert first["id"] == scan["id"]
    assert first["lease_owner"] == "worker-a"
    assert _claim_scan(worker_id="worker-b") is None

    from ai_os.db import connect
    with connect() as db:
        db.execute(
            "UPDATE discovery_scans SET lease_expires_at='2000-01-01T00:00:00+00:00' WHERE id=?",
            (scan["id"],),
        )

    recovered = _claim_scan(worker_id="worker-b")
    assert recovered is not None
    assert recovered["id"] == scan["id"]
    assert recovered["lease_owner"] == "worker-b"
    assert recovered["attempts"] == 2


def test_legacy_worker_service_imports_without_missing_agent_modules():
    import ai_os.worker_service as worker_service
    assert callable(worker_service.main)
