import sqlite3

import pytest
from fastapi.testclient import TestClient

from opencompany_app.api import app, get_runtime, get_store, require_owner_key
from opencompany_app.runtime import create_runtime


@pytest.fixture
def backup_client(tmp_path):
    runtime = create_runtime(str(tmp_path / "live.sqlite3"))
    with runtime.store._lock:
        runtime.store._connection.execute("CREATE TABLE backup_probe(value TEXT NOT NULL)")
        runtime.store._connection.execute("INSERT INTO backup_probe(value) VALUES('snapshot-ok')")
    app.dependency_overrides[get_runtime] = lambda: runtime
    app.dependency_overrides[get_store] = lambda: runtime.store
    app.dependency_overrides[require_owner_key] = lambda: "owner"
    with TestClient(app) as client:
        yield client, tmp_path
    app.dependency_overrides.clear()
    runtime.close()


def test_owner_backup_download_is_consistent_and_integrity_checked(backup_client):
    client, tmp_path = backup_client
    response = client.get("/owner/backup")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "attachment;" in response.headers["content-disposition"]
    backup_path = tmp_path / "downloaded.sqlite3"
    backup_path.write_bytes(response.content)
    with sqlite3.connect(backup_path) as backup:
        assert backup.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert backup.execute("SELECT value FROM backup_probe").fetchone()[0] == "snapshot-ok"


def test_backup_destination_cannot_overwrite_live_database(tmp_path):
    runtime = create_runtime(str(tmp_path / "live.sqlite3"))
    try:
        with pytest.raises(ValueError, match="must differ"):
            runtime.store.backup_to(tmp_path / "live.sqlite3")
    finally:
        runtime.close()

def test_owner_backup_endpoint_rejects_unauthenticated_requests(monkeypatch, tmp_path):
    from opencompany_app.api import _default_runtime

    monkeypatch.setenv("OPENCOMPANY_OWNER_API_KEY", "test-owner-key")
    monkeypatch.setenv("OPENCOMPANY_DATABASE_PATH", str(tmp_path / "auth-live.sqlite3"))
    _default_runtime.cache_clear()
    try:
        with TestClient(app) as client:
            response = client.get("/owner/backup")
        assert response.status_code == 401
    finally:
        if _default_runtime.cache_info().currsize:
            _default_runtime().close()
            _default_runtime.cache_clear()
