from fastapi.testclient import TestClient

from ai_os.api import app


def test_health():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_task_and_approval_flow():
    with TestClient(app) as client:
        task = client.post("/tasks", json={"title": "Research demand", "department": "research"})
        assert task.status_code == 201
        approval = client.post("/approvals", json={
            "task_id": task.json()["id"], "action": "publish_content"
        })
        assert approval.status_code == 201
        aid = approval.json()["id"]
        decision = client.post(f"/approvals/{aid}/decision", json={"decision": "rejected"})
        assert decision.status_code == 200
        assert decision.json()["status"] == "rejected"


def test_approval_cannot_be_decided_twice():
    with TestClient(app) as client:
        approval = client.post("/approvals", json={"action": "spend_money"}).json()
        aid = approval["id"]
        assert client.post(
            f"/approvals/{aid}/decision", json={"decision": "approved"}
        ).status_code == 200
        assert client.post(
            f"/approvals/{aid}/decision", json={"decision": "rejected"}
        ).status_code == 409


def test_production_routes_require_api_key(monkeypatch):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_API_KEY", "test-owner-key")
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/tasks").status_code == 401
        assert client.get("/tasks", headers={"X-API-Key": "wrong"}).status_code == 401
        assert client.get("/tasks", headers={"X-API-Key": "test-owner-key"}).status_code == 200


def test_non_development_requires_api_key_at_startup(monkeypatch):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.delenv("AI_OS_API_KEY", raising=False)
    try:
        with TestClient(app):
            raise AssertionError("Application startup should reject a missing API key")
    except RuntimeError as exc:
        assert "AI_OS_API_KEY" in str(exc)


def test_owner_dashboard_is_served():
    with TestClient(app) as client:
        response = client.get("/owner")
    assert response.status_code == 200
    assert "AI Company Control Center" in response.text
    assert "Queue scan" in response.text


def test_discovery_scan_queue_and_read_endpoints():
    with TestClient(app) as client:
        response = client.post("/discovery/scans", json={"categories": ["agent-frameworks"]})
        assert response.status_code == 202
        scan = response.json()
        assert scan["status"] == "queued"
        scans = client.get("/discovery/scans")
        assert scans.status_code == 200
        assert any(item["id"] == scan["id"] for item in scans.json())
        candidates = client.get("/discovery/candidates")
        assert candidates.status_code == 200


def test_discovery_status_reports_live_github_check_without_secret(monkeypatch):
    from ai_os import api

    monkeypatch.setattr(api, "github_api_status", lambda: {
        "connected": True, "authentication": "public-unauthenticated",
        "token_configured": False, "search_remaining": 10, "search_limit": 10,
        "checked_at": "2026-11-09T00:00:00+00:00", "error": None,
    })
    with TestClient(app) as client:
        response = client.get("/discovery/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["github"]["connected"] is True
    assert payload["github"]["token_configured"] is False
    assert "worker_running" in payload
    assert "api_key" not in payload["github"]
    assert "authorization" not in payload["github"]


def test_free_api_catalog_read_endpoint(monkeypatch):
    from ai_os import api

    monkeypatch.setattr(api, "list_free_api_catalog", lambda category=None: {
        "provider_count": 1, "providers": [{"id": "sample"}],
        "secondary_sources": [], "safety": "research leads only",
    })
    with TestClient(app) as client:
        response = client.get("/discovery/provider-catalog")
    assert response.status_code == 200
    assert response.json()["provider_count"] == 1


def test_free_api_catalog_sync_is_owner_controlled(monkeypatch):
    from ai_os import api

    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_API_KEY", "test-owner-key")
    monkeypatch.setattr(api, "sync_free_api_catalog", lambda: {
        "imported": 79, "source": "IdoY12/awesome-free-ai-apis",
        "important": "No provider was enabled.",
    })
    with TestClient(app) as client:
        response = client.post(
            "/discovery/provider-catalog/sync",
            headers={"X-API-Key": "test-owner-key"},
            json={},
        )
    assert response.status_code == 200
    assert response.json()["imported"] == 79


def test_discovery_scan_rejects_empty_categories():
    with TestClient(app) as client:
        response = client.post("/discovery/scans", json={"categories": []})
    assert response.status_code == 422


def test_recover_interrupted_agent_run(monkeypatch, tmp_path):
    from ai_os.agent_runtime import recover_interrupted_runs
    from ai_os.db import connect, initialize_database

    monkeypatch.setenv("AI_OS_DATABASE_URL", "sqlite:///" + str(tmp_path / "agent-recovery.db"))
    initialize_database()
    with connect() as db:
        db.execute(
            "INSERT INTO tasks (id,title,description,department,status,created_at) VALUES (?,?,?,?,?,?)",
            ("task-1", "Research", "", "research", "running", "2026-01-01T00:00:00+00:00"),
        )
        db.execute(
            "INSERT INTO agent_runs (id,task_id,status,created_at,started_at) VALUES (?,?,?,?,?)",
            ("run-1", "task-1", "running", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:01+00:00"),
        )
        db.execute(
            """INSERT INTO agent_run_steps
            (run_id,sequence_no,role,agent_id,agent_name,status,input_summary,created_at)
            VALUES (?,?,?,?,?,?,?,?)""",
            ("run-1", 1, "Lead specialist", "researcher", "Researcher", "running", "Research", "2026-01-01T00:00:02+00:00"),
        )

    assert recover_interrupted_runs() == 1
    assert recover_interrupted_runs() == 0
    with connect() as db:
        run = db.execute("SELECT status,error,finished_at FROM agent_runs WHERE id='run-1'").fetchone()
        task = db.execute("SELECT status FROM tasks WHERE id='task-1'").fetchone()
        step = db.execute("SELECT status,error,finished_at FROM agent_run_steps WHERE run_id='run-1'").fetchone()
        event = db.execute("SELECT stage FROM agent_run_events WHERE run_id='run-1' ORDER BY id DESC LIMIT 1").fetchone()

    assert run["status"] == "failed"
    assert "interrupted" in run["error"].lower()
    assert run["finished_at"]
    assert task["status"] == "failed"
    assert step["status"] == "failed"
    assert step["finished_at"]
    assert event["stage"] == "interrupted"



def test_unorouter_personal_test_requires_owner_auth(monkeypatch):
    with TestClient(app) as client:
        response = client.post("/llm/unorouter/personal-test", json={"provider":"unorouter","prompt":"synthetic test"})
    assert response.status_code in (401, 403)


def test_api_anything_routes_require_owner_auth(monkeypatch):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_API_KEY", "test-owner-key")
    with TestClient(app) as client:
        assert client.get("/integrations/api-anything/status").status_code == 401
        response = client.get(
            "/integrations/api-anything/status",
            headers={"X-API-Key": "test-owner-key"},
        )
    assert response.status_code == 200
    assert response.json()["configured"] is False


def test_api_anything_read_call_is_owner_only_and_forwards_safe_request(monkeypatch):
    from ai_os import api

    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_API_KEY", "test-owner-key")
    captured = {}

    def fake_call(site, operation, args, fields=None):
        captured.update(site=site, operation=operation, args=args, fields=fields)
        return {"ok": True, "data": [{"title": "SQLite"}]}

    monkeypatch.setattr(api.website_api, "call_read", fake_call)
    with TestClient(app) as client:
        denied = client.post(
            "/integrations/api-anything/call/hacker-news/search",
            json={"args": {"query": "sqlite"}},
        )
        allowed = client.post(
            "/integrations/api-anything/call/hacker-news/search",
            headers={"X-API-Key": "test-owner-key"},
            json={"args": {"query": "sqlite"}},
        )
    assert denied.status_code == 401
    assert allowed.status_code == 200
    assert captured == {
        "site": "hacker-news",
        "operation": "search",
        "args": {"query": "sqlite"},
        "fields": None,
    }



def test_code_asset_repository_url_validation():
    from ai_os.code_assets import _repo_parts, _eligible_source

    assert _repo_parts("https://github.com/example/project.git") == (
        "example", "project", "https://github.com/example/project"
    )
    for unsafe in (
        "http://github.com/example/project",
        "https://evil.example/example/project",
        "file:///etc/passwd",
    ):
        try:
            _repo_parts(unsafe)
            raise AssertionError("Unsafe repository URL should be rejected")
        except ValueError:
            pass

    assert _eligible_source("src/main.py") is True
    assert _eligible_source(".env") is False
    assert _eligible_source("vendor/lib/secret.py") is False
    assert _eligible_source("package-lock.json") is False


def test_code_asset_scan_requires_owner_auth(monkeypatch):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_API_KEY", "test-owner-key")
    from ai_os import api

    monkeypatch.setattr(api.code_assets, "scan_repository", lambda url: {
        "id": "asset-test", "repository_url": url, "readiness": "needs-evidence"
    })
    with TestClient(app) as client:
        denied = client.post("/code-assets/scan", json={
            "repository_url": "https://github.com/example/project"
        })
        allowed = client.post("/code-assets/scan", headers={
            "X-API-Key": "test-owner-key"
        }, json={"repository_url": "https://github.com/example/project"})
        listed = client.get("/code-assets", headers={"X-API-Key": "test-owner-key"})

    assert denied.status_code == 401
    assert allowed.status_code == 201
    assert allowed.json()["readiness"] == "needs-evidence"
    assert listed.status_code == 200
