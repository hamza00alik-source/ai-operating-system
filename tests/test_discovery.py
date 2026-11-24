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
            "sources": [{"title": "Official docs", "url": "https://example.com/docs", "accessed": "2026-11-08"}],
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
    assert provider["sources"][0]["url"] == "https://example.com/docs"
    assert provider["review_state"] == "pending"
    assert provider["evidence_freshness"]["state"] == "stale"
    assert provider["routing_eligible"] is False
    assert "never enable or authorize" in provider["routing_note"].lower()
    assert listed["evidence_freshness"]["counts"]["stale"] == 1
    assert "no provider was enabled" in result["important"].lower()


def test_discovery_scan_claim_and_lease_ownership(monkeypatch, tmp_path):
    from ai_os.discovery import claim_next_scan, renew_scan_lease
    monkeypatch.setenv('AI_OS_DATABASE_URL', f"sqlite:///{tmp_path / 'discovery-lease.db'}")
    initialize_database()
    scan = create_scan(['agent-frameworks'])
    claimed = claim_next_scan('worker-a', lease_seconds=120)
    assert claimed['id'] == scan['id']
    assert claimed['lease_owner'] == 'worker-a'
    assert claim_next_scan('worker-b') is None
    assert renew_scan_lease(scan['id'], 'worker-b') is False
    assert renew_scan_lease(scan['id'], 'worker-a') is True


def test_discovery_recovery_fails_expired_scan_without_requeue(monkeypatch, tmp_path):
    from ai_os.discovery import recover_interrupted_scans
    from ai_os.db import connect
    monkeypatch.setenv('AI_OS_DATABASE_URL', f"sqlite:///{tmp_path / 'discovery-recovery.db'}")
    initialize_database()
    scan = create_scan(['agent-frameworks'])
    with connect() as db:
        db.execute("UPDATE discovery_scans SET status='running',lease_owner='dead-worker',lease_expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (scan['id'],))
    assert recover_interrupted_scans() == 1
    with connect() as db:
        row = db.execute('SELECT status,lease_owner,lease_expires_at FROM discovery_scans WHERE id=?', (scan['id'],)).fetchone()
    assert row['status'] == 'failed'
    assert row['lease_owner'] is None and row['lease_expires_at'] is None
    assert recover_interrupted_scans() == 0


def test_discovery_recovery_preserves_live_lease(monkeypatch, tmp_path):
    from datetime import datetime, timedelta, timezone
    from ai_os.discovery import recover_interrupted_scans
    from ai_os.db import connect
    monkeypatch.setenv('AI_OS_DATABASE_URL', f"sqlite:///{tmp_path / 'discovery-live.db'}")
    initialize_database()
    scan = create_scan(['agent-frameworks'])
    future = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    with connect() as db:
        db.execute("UPDATE discovery_scans SET status='running',lease_owner='active-worker',lease_expires_at=? WHERE id=?", (future, scan['id']))
    assert recover_interrupted_scans() == 0
    with connect() as db:
        assert db.execute('SELECT status FROM discovery_scans WHERE id=?', (scan['id'],)).fetchone()['status'] == 'running'


def test_discovery_scan_stops_when_lease_is_lost(monkeypatch, tmp_path):
    from ai_os import discovery
    from ai_os.db import connect
    monkeypatch.setenv('AI_OS_DATABASE_URL', f"sqlite:///{tmp_path / 'discovery-fence.db'}")
    initialize_database()
    scan = create_scan(['agent-frameworks'])
    discovery.claim_next_scan('owner-a')
    monkeypatch.setattr(discovery, '_github_search', lambda _query: [{'html_url': 'https://github.com/a/b', 'license': {'spdx_id': 'MIT'}}])
    monkeypatch.setattr(discovery, '_assert_scan_lease', lambda *_args: (_ for _ in ()).throw(RuntimeError('lease lost')))
    import pytest
    with pytest.raises(RuntimeError, match='lease lost'):
        discovery.run_scan(scan['id'], 'owner-a', already_claimed=True)
    with connect() as db:
        assert db.execute('SELECT COUNT(*) AS n FROM discovery_candidates').fetchone()['n'] == 0



def test_expired_discovery_lease_cannot_be_renewed(monkeypatch, tmp_path):
    from ai_os.discovery import claim_next_scan, renew_scan_lease
    from ai_os.db import connect
    monkeypatch.setenv('AI_OS_DATABASE_URL', f"sqlite:///{tmp_path / 'discovery-expired-renew.db'}")
    initialize_database()
    scan = create_scan(['agent-frameworks'])
    claim_next_scan('worker-a')
    with connect() as db:
        db.execute("UPDATE discovery_scans SET lease_expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (scan['id'],))
    assert renew_scan_lease(scan['id'], 'worker-a') is False



def test_expired_discovery_worker_cannot_write_failure_state(monkeypatch, tmp_path):
    from ai_os import discovery
    from ai_os.db import connect
    monkeypatch.setenv('AI_OS_DATABASE_URL', f"sqlite:///{tmp_path / 'discovery-stale-failure.db'}")
    initialize_database()
    scan = create_scan(['agent-frameworks'])
    discovery.claim_next_scan('worker-a')

    def expire_then_return(_query):
        with connect() as db:
            db.execute("UPDATE discovery_scans SET lease_expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (scan['id'],))
        return []

    monkeypatch.setattr(discovery, '_github_search', expire_then_return)
    with pytest.raises(RuntimeError, match='lease'):
        discovery.run_scan(scan['id'], 'worker-a', already_claimed=True)
    with connect() as db:
        row = db.execute("SELECT status,lease_owner FROM discovery_scans WHERE id=?", (scan['id'],)).fetchone()
    assert row['status'] == 'running'
    assert row['lease_owner'] == 'worker-a'



def test_provider_evidence_freshness_uses_verification_date_conservatively():
    from datetime import datetime, timedelta, timezone
    from ai_os.discovery import _evidence_freshness

    recent = (datetime.now(timezone.utc) - timedelta(days=4)).date().isoformat()
    stale = (datetime.now(timezone.utc) - timedelta(days=45)).date().isoformat()
    assert _evidence_freshness(recent, [{"accessed": stale}])["state"] == "recent"
    old_verification = _evidence_freshness(stale, [{"accessed": recent}])
    assert old_verification["state"] == "stale"
    assert "last_verified" in old_verification["basis"]
    assert _evidence_freshness(None, [])["state"] == "unknown"
