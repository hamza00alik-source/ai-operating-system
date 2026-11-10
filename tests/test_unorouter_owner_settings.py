import json
import sqlite3
from threading import RLock

from fastapi.testclient import TestClient

from opencompany_app import api
from opencompany_app.runtime import create_runtime
from opencompany_core import unorouter_adapter


def test_owner_can_manage_encrypted_unorouter_credentials_without_key_echo(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENCOMPANY_OWNER_API_KEY", "owner-api-key-for-tests-long-enough-123456")
    monkeypatch.setenv("OPENCOMPANY_SECRET_ENCRYPTION_KEY", "test-encryption-key-at-least-32-characters")
    runtime = create_runtime(str(tmp_path / "owner.sqlite3"))
    api.app.dependency_overrides[api.get_runtime] = lambda: runtime
    client = TestClient(api.app)
    try:
        denied = client.get("/settings/providers/unorouter")
        assert denied.status_code == 401
        saved = client.put("/settings/providers/unorouter", headers={"X-OpenCompany-API-Key": "owner-api-key-for-tests-long-enough-123456"},
            json={"api_key":"unorouter-private-api-key-value","model":"qwen/model:free","confirm_free":True})
        assert saved.status_code == 200
        assert "unorouter-private-api-key-value" not in saved.text
        status = client.get("/settings/providers/unorouter", headers={"X-OpenCompany-API-Key": "owner-api-key-for-tests-long-enough-123456"})
        assert status.status_code == 200
        assert status.json()["configured"] is True
        assert status.json()["model"] == "qwen/model:free"
        assert status.json()["api_key_present"] is True
        assert "unorouter-private-api-key-value" not in status.text
        removed = client.delete("/settings/providers/unorouter", headers={"X-OpenCompany-API-Key": "owner-api-key-for-tests-long-enough-123456"})
        assert removed.status_code == 200
        assert removed.json()["configured"] is False
    finally:
        api.app.dependency_overrides.clear()
        runtime.close()


def test_dashboard_includes_owner_only_unorouter_settings_controls():
    response = TestClient(api.app).get("/owner")
    assert response.status_code == 200
    assert 'id="unorouter-api-key"' in response.text
    assert 'id="unorouter-test"' in response.text
    assert "/settings/providers/unorouter" in response.text


def test_owner_triggered_connection_test_uses_only_saved_free_route(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENCOMPANY_OWNER_API_KEY", "owner-api-key-for-tests-long-enough-123456")
    monkeypatch.setenv("OPENCOMPANY_SECRET_ENCRYPTION_KEY", "test-encryption-key-at-least-32-characters")
    monkeypatch.setenv("OPENCOMPANY_WORKER_AUTOSTART", "true")
    from opencompany_core import unorouter_adapter

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, limit):
            return json.dumps({
                "model": "qwen/model:free",
                "choices": [{"message": {"content": "OPENCOMPANY_UNOROUTER_OK"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 4, "cost": 0},
            }).encode()

    captured = {}
    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data)
        return FakeResponse()

    monkeypatch.setattr(unorouter_adapter, "urlopen", fake_urlopen)
    runtime = create_runtime(str(tmp_path / "test.sqlite3"))
    worker_starts = []
    runtime.fleet.start = lambda: worker_starts.append(True) or True
    api.app.dependency_overrides[api.get_runtime] = lambda: runtime
    client = TestClient(api.app)
    headers = {"X-OpenCompany-API-Key": "owner-api-key-for-tests-long-enough-123456"}
    try:
        saved = client.put("/settings/providers/unorouter", headers=headers,
            json={"api_key":"private-unorouter-token-123456","model":"qwen/model:free","confirm_free":True})
        assert saved.status_code == 200
        assert worker_starts == []
        tested = client.post("/settings/providers/unorouter/test", headers=headers, json={})
        assert tested.status_code == 200
        assert tested.json()["cost_usd"] == 0
        assert tested.json()["paid_fallback"] is False
        assert tested.json()["worker_autostart_enabled"] is True
        assert tested.json()["worker_started"] is True
        assert worker_starts == [True]
        assert captured["url"] == "https://api.unorouter.com/v1/chat/completions"
        assert captured["payload"]["model"] == "qwen/model:free"
        status = client.get("/settings/providers/unorouter", headers=headers)
        assert status.json()["real_inference_verified"] is True
    finally:
        api.app.dependency_overrides.clear()
        runtime.close()


def test_runtime_reloads_encrypted_unorouter_credentials_after_restart(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENCOMPANY_OWNER_API_KEY", "owner-api-key-for-tests-long-enough-123456")
    monkeypatch.setenv("OPENCOMPANY_SECRET_ENCRYPTION_KEY", "test-encryption-key-at-least-32-characters")
    monkeypatch.setenv("OPENCOMPANY_WORKER_AUTOSTART", "true")
    monkeypatch.setenv("OPENCOMPANY_GITHUB_REPOSITORY", "hamza00alik-source/ai-operating-system")
    path = str(tmp_path / "persisted.sqlite3")
    first = create_runtime(path)
    first.secret_vault.put("unorouter", {"api_key":"private-unorouter-token-123456","model":"qwen/model:free"})
    first.secret_vault.put("github_evolution", {"token":"github-fine-grained-token-private-value-123456"})
    first.close()
    second = create_runtime(path)
    try:
        assert second.gateway.eligible_providers(request_budget_usd=0) == ("unorouter",)
        assert second.github_evolution is not None
        assert second.github_evolution.repository == "hamza00alik-source/ai-operating-system"
        assert second.fleet.status().running is False
        assert second.start_workers_if_ready() is False
    finally:
        second.close()


def test_provider_credentials_are_not_changed_if_running_workers_cannot_stop(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENCOMPANY_OWNER_API_KEY", "owner-api-key-for-tests-long-enough-123456")
    monkeypatch.setenv("OPENCOMPANY_SECRET_ENCRYPTION_KEY", "test-encryption-key-at-least-32-characters")
    runtime = create_runtime(str(tmp_path / "busy-worker.sqlite3"))
    class Running:
        running = True
    runtime.fleet.stop = lambda timeout_seconds=5.0: False
    runtime.fleet.status = lambda: Running()
    api.app.dependency_overrides[api.get_runtime] = lambda: runtime
    client = TestClient(api.app)
    try:
        response = client.put(
            "/settings/providers/unorouter",
            headers={"X-OpenCompany-API-Key": "owner-api-key-for-tests-long-enough-123456"},
            json={"api_key": "private-unorouter-token-123456", "model": "qwen/model:free", "confirm_free": True},
        )
        assert response.status_code == 409
        assert runtime.secret_vault.get("unorouter") is None
    finally:
        api.app.dependency_overrides.clear()
        runtime.close()



def test_provider_dashboard_explains_verified_worker_autostart():
    response = TestClient(api.app).get("/owner")
    assert response.status_code == 200
    assert "worker fleet starts automatically only when owner-configured autostart is enabled" in response.text
    assert "Worker fleet started automatically." in response.text


def test_owner_can_manage_encrypted_github_evolution_token_without_echo(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENCOMPANY_OWNER_API_KEY", "owner-api-key-for-tests-long-enough-123456")
    monkeypatch.setenv("OPENCOMPANY_SECRET_ENCRYPTION_KEY", "test-encryption-key-at-least-32-characters")
    monkeypatch.setenv("OPENCOMPANY_GITHUB_REPOSITORY", "hamza00alik-source/ai-operating-system")
    monkeypatch.setenv("OPENCOMPANY_GITHUB_BASE_BRANCH", "clean-room-rebuild")
    runtime = create_runtime(str(tmp_path / "github-owner.sqlite3"))
    api.app.dependency_overrides[api.get_runtime] = lambda: runtime
    client = TestClient(api.app)
    headers = {"X-OpenCompany-API-Key": "owner-api-key-for-tests-long-enough-123456"}
    try:
        denied = client.get("/settings/integrations/github-evolution")
        assert denied.status_code == 401
        saved = client.put(
            "/settings/integrations/github-evolution", headers=headers,
            json={"token": "github-fine-grained-token-private-value-123456",
                  "confirm_draft_pr_only": True},
        )
        assert saved.status_code == 200
        assert "github-fine-grained-token-private-value-123456" not in saved.text
        status = client.get("/settings/integrations/github-evolution", headers=headers)
        assert status.status_code == 200
        assert status.json()["configured"] is True
        assert status.json()["token_present"] is True
        assert status.json()["auto_merge"] is False
        assert status.json()["auto_deploy"] is False
        assert "github-fine-grained-token-private-value-123456" not in status.text
        runtime.github_evolution.verify_access = lambda: {
            "authenticated": True, "username": "test-owner",
            "repository_access": True, "repository": "hamza00alik-source/ai-operating-system",
            "base_branch": "clean-room-rebuild", "push_permission_reported": True,
            "verification_mode": "read_only", "auto_merge": False, "auto_deploy": False,
        }
        tested = client.post("/settings/integrations/github-evolution/test", headers=headers, json={})
        assert tested.status_code == 200
        assert tested.json()["verification_mode"] == "read_only"
        removed = client.delete("/settings/integrations/github-evolution", headers=headers)
        assert removed.status_code == 200
        assert removed.json()["configured"] is False
    finally:
        api.app.dependency_overrides.clear()
        runtime.close()


def test_github_evolution_token_requires_explicit_draft_only_confirmation(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENCOMPANY_OWNER_API_KEY", "owner-api-key-for-tests-long-enough-123456")
    monkeypatch.setenv("OPENCOMPANY_SECRET_ENCRYPTION_KEY", "test-encryption-key-at-least-32-characters")
    monkeypatch.setenv("OPENCOMPANY_GITHUB_REPOSITORY", "hamza00alik-source/ai-operating-system")
    runtime = create_runtime(str(tmp_path / "github-confirm.sqlite3"))
    api.app.dependency_overrides[api.get_runtime] = lambda: runtime
    client = TestClient(api.app)
    try:
        response = client.put(
            "/settings/integrations/github-evolution",
            headers={"X-OpenCompany-API-Key": "owner-api-key-for-tests-long-enough-123456"},
            json={"token": "github-fine-grained-token-private-value-123456",
                  "confirm_draft_pr_only": False},
        )
        assert response.status_code == 422
        assert runtime.secret_vault.get("github_evolution") is None
    finally:
        api.app.dependency_overrides.clear()
        runtime.close()


def test_startup_recovers_from_encryption_key_rotation_and_allows_secret_replacement(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENCOMPANY_OWNER_API_KEY", "owner-api-key-for-tests-long-enough-123456")
    monkeypatch.setenv("OPENCOMPANY_SECRET_ENCRYPTION_KEY", "first-encryption-key-at-least-32-characters")
    monkeypatch.setenv("OPENCOMPANY_GITHUB_REPOSITORY", "hamza00alik-source/ai-operating-system")
    path = str(tmp_path / "rotated-key.sqlite3")
    first = create_runtime(path)
    first.secret_vault.put("unorouter", {"api_key": "old-unorouter-key-private-123456", "model": "qwen/model:free"})
    first.secret_vault.put("github_evolution", {"token": "old-github-token-private-123456789"})
    first.close()

    monkeypatch.setenv("OPENCOMPANY_SECRET_ENCRYPTION_KEY", "second-encryption-key-at-least-32-characters")
    runtime = create_runtime(path)
    api.app.dependency_overrides[api.get_runtime] = lambda: runtime
    client = TestClient(api.app)
    headers = {"X-OpenCompany-API-Key": "owner-api-key-for-tests-long-enough-123456"}
    try:
        assert runtime.gateway.eligible_providers(request_budget_usd=0.0) == ()
        assert runtime.github_evolution is None
        assert set(runtime.secret_vault_errors) == {"unorouter", "github_evolution"}
        github_status = client.get("/settings/integrations/github-evolution", headers=headers)
        assert github_status.status_code == 200
        assert github_status.json()["token_present"] is True
        assert github_status.json()["configuration_error"] is not None

        replaced_uno = client.put(
            "/settings/providers/unorouter", headers=headers,
            json={"api_key": "new-unorouter-key-private-123456", "model": "qwen/model:free", "confirm_free": True},
        )
        assert replaced_uno.status_code == 200
        assert "unorouter" not in runtime.secret_vault_errors
        assert runtime.gateway.eligible_providers(request_budget_usd=0.0) == ("unorouter",)

        replaced_github = client.put(
            "/settings/integrations/github-evolution", headers=headers,
            json={"token": "new-github-token-private-123456789",
                  "confirm_draft_pr_only": True},
        )
        assert replaced_github.status_code == 200
        assert "github_evolution" not in runtime.secret_vault_errors
        assert runtime.github_evolution is not None
    finally:
        api.app.dependency_overrides.clear()
        runtime.close()


def test_code_evolution_requires_read_only_github_access_verification(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENCOMPANY_OWNER_API_KEY", "owner-api-key-for-tests-long-enough-123456")
    monkeypatch.setenv("OPENCOMPANY_SECRET_ENCRYPTION_KEY", "test-encryption-key-at-least-32-characters")
    monkeypatch.setenv("OPENCOMPANY_GITHUB_REPOSITORY", "hamza00alik-source/ai-operating-system")
    runtime = create_runtime(str(tmp_path / "github-verify-gate.sqlite3"))
    api.app.dependency_overrides[api.get_runtime] = lambda: runtime
    client = TestClient(api.app)
    headers = {"X-OpenCompany-API-Key": "owner-api-key-for-tests-long-enough-123456"}
    try:
        saved = client.put(
            "/settings/integrations/github-evolution", headers=headers,
            json={"token": "github-fine-grained-token-private-value-123456",
                  "confirm_draft_pr_only": True},
        )
        assert saved.status_code == 200
        runtime.github_evolution.verify_access = lambda: {
            "authenticated": True, "username": "test-owner",
            "repository_access": True, "repository": "hamza00alik-source/ai-operating-system",
            "base_branch": "clean-room-rebuild", "push_permission_reported": True,
            "verification_mode": "read_only", "auto_merge": False, "auto_deploy": False,
        }
        blocked = client.post(
            "/code-evolution/proposals", headers=headers,
            json={"problem": "Improve safe request validation", "file_paths": ["src/opencompany_core/model_gateway.py"]},
        )
        assert blocked.status_code == 409
        verified = client.post("/settings/integrations/github-evolution/test", headers=headers, json={})
        assert verified.status_code == 200
        status = client.get("/code-evolution/config-status", headers=headers)
        assert status.status_code == 200
        assert status.json()["configured"] is True
        assert status.json()["access_verified"] is True
        assert status.json()["enabled"] is True
    finally:
        api.app.dependency_overrides.clear()
        runtime.close()
