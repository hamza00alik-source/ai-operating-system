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
