from opencompany_app.runtime import create_runtime


def test_worker_fleet_autostarts_only_when_owner_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCOMPANY_DATABASE_PATH", str(tmp_path / "runtime.sqlite3"))
    monkeypatch.setenv("OPENCOMPANY_WORKER_AUTOSTART", "true")
    runtime = create_runtime()
    try:
        assert runtime.fleet.status().running is True
    finally:
        runtime.close()


def test_worker_fleet_stays_stopped_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCOMPANY_DATABASE_PATH", str(tmp_path / "runtime.sqlite3"))
    monkeypatch.delenv("OPENCOMPANY_WORKER_AUTOSTART", raising=False)
    runtime = create_runtime()
    try:
        assert runtime.fleet.status().running is False
    finally:
        runtime.close()
