from fastapi.testclient import TestClient

from ai_os.api import app
from ai_os.db import connect, initialize_database


def test_agent_run_details_and_retry_cannot_cross_business_scope(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", "sqlite:///" + str(tmp_path / "run-scope.db"))
    with TestClient(app) as client:
        initialize_database()
        with connect() as db:
            db.execute(
                "INSERT INTO tasks (id,title,department,business_id,status,created_at) VALUES (?,?,?,?,?,?)",
                ("agency-task", "Agency buyer research", "sales", "physical-agency", "completed", "2026-01-01T00:00:00+00:00"),
            )
            db.execute(
                "INSERT INTO agent_runs (id,task_id,status,created_at) VALUES (?,?,?,?)",
                ("agency-run", "agency-task", "completed", "2026-01-01T00:00:00+00:00"),
            )
            db.execute(
                "INSERT INTO agent_run_events (run_id,stage,message,created_at) VALUES (?,?,?,?)",
                ("agency-run", "completed", "Agency-only event", "2026-01-01T00:00:00+00:00"),
            )
            db.execute(
                """INSERT INTO agent_run_steps
                (run_id,sequence_no,role,agent_id,agent_name,status,input_summary,output,created_at)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                ("agency-run", 1, "sales", "agency-agent", "Agency Agent", "completed", "", "Agency-only output", "2026-01-01T00:00:00+00:00"),
            )

        assert client.get("/agent-runs/agency-run?business_id=physical-agency").status_code == 200
        assert client.get("/agent-runs/agency-run/events?business_id=physical-agency").json()[0]["message"] == "Agency-only event"
        assert client.get("/agent-runs/agency-run/steps?business_id=physical-agency").json()[0]["output"] == "Agency-only output"

        # All identifier-based detail surfaces conceal records belonging to another business.
        assert client.get("/agent-runs/agency-run?business_id=physical-brand").status_code == 404
        assert client.get("/agent-runs/agency-run/events?business_id=physical-brand").status_code == 404
        assert client.get("/agent-runs/agency-run/steps?business_id=physical-brand").status_code == 404
        assert client.post("/agent-runs/agency-run/retry?business_id=physical-brand").status_code == 404
        assert client.get("/agent-runs/agency-run?business_id=unknown-business").status_code == 422
