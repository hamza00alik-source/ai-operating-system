from opencompany_app.runtime import create_runtime


def test_worker_fleet_stays_stopped_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCOMPANY_DATABASE_PATH", str(tmp_path / "runtime.sqlite3"))
    monkeypatch.delenv("OPENCOMPANY_WORKER_AUTOSTART", raising=False)
    runtime = create_runtime()
    try:
        assert runtime.fleet.status().running is False
    finally:
        runtime.close()


def test_api_startup_bootstraps_and_activates_all_roles_when_owner_configured(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from opencompany_app.api import app, _default_runtime
    monkeypatch.setenv("OPENCOMPANY_DATABASE_PATH", str(tmp_path / "startup.sqlite3"))
    monkeypatch.setenv("OPENCOMPANY_OWNER_API_KEY", "test-owner-key")
    monkeypatch.setenv("OPENCOMPANY_BOOTSTRAP_WORKFORCE", "true")
    monkeypatch.setenv("OPENCOMPANY_AUTO_ACTIVATE_WORKFORCE", "true")
    monkeypatch.setenv("OPENCOMPANY_UNOROUTER_API_KEY", "test-unorouter-key")
    monkeypatch.setenv("OPENCOMPANY_UNOROUTER_FREE_MODEL", "test/free-model:free")
    monkeypatch.setenv("OPENCOMPANY_CONFIRM_UNOROUTER_FREE", "true")
    monkeypatch.setenv("OPENCOMPANY_WORKER_AUTOSTART", "true")
    _default_runtime.cache_clear()
    with TestClient(app):
        runtime = _default_runtime()
        agents = runtime.store.list_agents(limit=1000)
        assert len(agents) == 511
        assert all(agent.state.value == "active" for agent in agents)
        # Saved credentials and legacy autostart flags do not substitute for
        # a live owner-triggered zero-cost provider verification in this process.
        assert runtime.fleet.status().running is False
        assert runtime.store.verify_audit_chain()
    assert _default_runtime.cache_info().currsize == 0
