"""Opt-in Product & R&D scheduler composition tests."""
from opencompany_app.runtime import create_runtime


def test_product_rd_scheduler_is_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCOMPANY_PRODUCT_RD_AUTOMATION", "false")
    monkeypatch.setenv("OPENCOMPANY_WORKER_AUTOSTART", "false")
    runtime = create_runtime(str(tmp_path / "automation-disabled.sqlite3"))
    try:
        assert runtime.automation_scheduler is None
        assert runtime.product_rd_auto_proposals_enabled is False
        assert runtime.fleet.status().maintenance_enabled is False
        assert runtime.fleet.status().running is False
    finally:
        runtime.close()


def test_product_rd_scheduler_opt_in_is_durable_but_does_not_start_workers(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCOMPANY_PRODUCT_RD_AUTOMATION", "true")
    monkeypatch.setenv("OPENCOMPANY_PRODUCT_RD_AUTO_PROPOSALS", "false")
    monkeypatch.setenv("OPENCOMPANY_WORKER_AUTOSTART", "false")
    runtime = create_runtime(str(tmp_path / "automation-opt-in.sqlite3"))
    try:
        assert runtime.automation_scheduler is not None
        assert runtime.product_rd_auto_proposals_enabled is False
        assert runtime.fleet.status().maintenance_enabled is True
        assert runtime.fleet.status().running is False
        jobs = runtime.automation_scheduler.status()
        assert len(jobs) == 1
        assert jobs[0]["job_id"] == "product_rd_maintenance"
        result = runtime.automation_scheduler.run_due()
        assert result == {"claimed": 1, "succeeded": 1, "failed": 0, "unregistered": 0}
        assert runtime.fleet.status().running is False
    finally:
        runtime.close()
