from ai_os.db import connect, initialize_database
from ai_os.executive_supervisor import executive_status, supervise_once
from ai_os.workflows import initialize_workflows


def _insert_task_and_failed_run():
    initialize_database()
    with connect() as db:
        db.execute(
            "INSERT INTO tasks(id,title,description,department,business_id,status,created_at) VALUES(?,?,?,?,?,?,?)",
            ("exec-test-task", "Test failed task", "", "research", "digital-products", "failed", "2026-01-01T00:00:00+00:00"),
        )
        db.execute(
            "INSERT INTO agent_runs(id,task_id,status,error,created_at) VALUES(?,?,?,?,?)",
            ("exec-test-run", "exec-test-task", "failed", "synthetic test failure", "2026-01-01T00:00:00+00:00"),
        )


def test_executive_supervisor_creates_idempotent_alerts():
    initialize_workflows()
    _insert_task_and_failed_run()
    first = supervise_once()
    second = supervise_once()
    assert first["alerts_created"] >= 1
    assert second["alerts_created"] == 0
    scope = next(x for x in executive_status("digital-products")["businesses"])
    assert scope["open_alert_count"] >= 1
    assert scope["agent_runs"].get("failed", 0) >= 1


def test_executive_status_keeps_businesses_separate():
    result = executive_status()
    ids = {item["business_id"] for item in result["businesses"]}
    assert {"physical-agency", "physical-brand", "digital-products"}.issubset(ids)
    assert result["policy"]["automatic_retry"] is False
    assert result["policy"]["external_actions"] is False
