from fastapi.testclient import TestClient

from ai_os import api


def test_owner_can_queue_bounded_agent_run(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_ENV", "development")
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'agent-runs.db'}")
    monkeypatch.setattr(api, "run_agent_pending_once", lambda: False)

    with TestClient(api.app) as client:
        task = client.post("/tasks", json={
            "title": "Prepare a market research brief",
            "description": "Identify customer segments and risks.",
            "department": "research",
        })
        assert task.status_code == 201
        task_id = task.json()["id"]

        queued = client.post(f"/tasks/{task_id}/execute")
        assert queued.status_code == 202
        assert queued.json()["status"] == "queued"

        run_id = queued.json()["id"]
        detail = client.get(f"/agent-runs/{run_id}")
        assert detail.status_code == 200
        assert detail.json()["task_id"] == task_id
        assert detail.json()["status"] == "queued"

        overview = client.get("/company/overview").json()
        assert overview["execution_runtime"] == "shared-worker-on-demand-specialist-plus-ceo-review"



def test_general_market_research_routes_to_research_role():
    from ai_os.agent_runtime import _select_specialist

    manifest = {
        "agents": [
            {"id": "marketing/global-podcast-strategist", "name": "Global Podcast Strategist",
             "department": "marketing", "source_path": ""},
            {"id": "research/research-synthesist", "name": "Research Synthesist",
             "department": "research", "source_path": ""},
        ]
    }
    selected = _select_specialist(
        {"title": "Prepare a global market research brief on downloadable PC gaming utilities",
         "description": "", "department": "general"},
        manifest,
    )
    assert selected["id"] == "research/research-synthesist"



def test_company_department_routes_to_mapped_specialist():
    from ai_os.agent_runtime import _select_specialist

    manifest = {
        "agents": [
            {"id": "engineering/backend-developer", "name": "Backend Developer",
             "department": "engineering", "source_path": ""},
            {"id": "support/customer-support-specialist", "name": "Customer Support Specialist",
             "department": "support", "source_path": ""},
        ]
    }
    selected = _select_specialist(
        {"title": "Prepare a customer response workflow", "description": "", "department": "customer-support"},
        manifest,
    )
    assert selected["id"] == "support/customer-support-specialist"


def test_partial_agent_run_can_be_resumed_without_repeating_completed_specialist(monkeypatch, tmp_path):
    from ai_os.agent_runtime import retry_run, _now
    from ai_os.db import connect, initialize_database

    monkeypatch.setenv("AI_OS_ENV", "development")
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'resume.db'}")
    initialize_database()
    with connect() as db:
        db.execute(
            "INSERT INTO tasks(id,title,description,department,status,created_at) VALUES(?,?,?,?,?,?)",
            ("task-1", "Research market", "", "research", "partial", _now()),
        )
        db.execute(
            "INSERT INTO agent_runs(id,task_id,status,specialist_output,created_at,finished_at,error) VALUES(?,?,?,?,?,?,?)",
            ("run-1", "task-1", "partial", "Saved specialist report", _now(), _now(), "collaborator provider failed"),
        )
        db.execute(
            """INSERT INTO agent_run_steps
            (run_id,sequence_no,role,agent_id,agent_name,status,input_summary,output,created_at,finished_at)
            VALUES(?,?,?,?,?,'completed',?,?,?,?)""",
            ("run-1", 1, "Lead specialist", "research/research-synthesist", "Research Synthesist",
             "Research market", "Saved specialist report", _now(), _now()),
        )
    queued = retry_run("run-1")
    assert queued["status"] == "queued"
    with connect() as db:
        assert db.execute("SELECT status FROM tasks WHERE id='task-1'").fetchone()["status"] == "queued"
        assert db.execute("SELECT output FROM agent_run_steps WHERE run_id='run-1' AND sequence_no=1").fetchone()["output"] == "Saved specialist report"


def test_agent_run_claim_is_atomic_and_persists_lease(monkeypatch, tmp_path):
    from ai_os.agent_runtime import claim_next_run, _now
    from ai_os.db import connect, initialize_database

    monkeypatch.setenv("AI_OS_ENV", "development")
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'leases.db'}")
    initialize_database()
    with connect() as db:
        db.execute(
            "INSERT INTO tasks(id,title,description,department,status,created_at) VALUES(?,?,?,?,?,?)",
            ("lease-task", "Lease test", "", "research", "queued", _now()),
        )
        db.execute(
            "INSERT INTO agent_runs(id,task_id,status,created_at) VALUES(?,?,?,?)",
            ("lease-run", "lease-task", "queued", _now()),
        )

    claim = claim_next_run("worker-a", lease_seconds=300)
    assert claim["run_id"] == "lease-run"
    with connect() as db:
        row = db.execute("SELECT status,lease_owner,lease_expires_at FROM agent_runs WHERE id='lease-run'").fetchone()
    assert row["status"] == "running"
    assert row["lease_owner"] == "worker-a"
    assert row["lease_expires_at"]
    assert claim_next_run("worker-b") is None


def test_interrupted_run_recovery_clears_lease_without_requeue(monkeypatch, tmp_path):
    from ai_os.agent_runtime import recover_interrupted_runs, _now
    from ai_os.db import connect, initialize_database

    monkeypatch.setenv("AI_OS_ENV", "development")
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'recover-lease.db'}")
    initialize_database()
    with connect() as db:
        db.execute(
            "INSERT INTO tasks(id,title,description,department,status,created_at) VALUES(?,?,?,?,?,?)",
            ("recover-task", "Recovery test", "", "research", "running", _now()),
        )
        db.execute(
            "INSERT INTO agent_runs(id,task_id,status,created_at,lease_owner,lease_expires_at) VALUES(?,?,?,?,?,?)",
            ("recover-run", "recover-task", "running", _now(), "dead-worker", "2000-01-01T00:00:00+00:00"),
        )

    assert recover_interrupted_runs() == 1
    with connect() as db:
        row = db.execute("SELECT status,lease_owner,lease_expires_at FROM agent_runs WHERE id='recover-run'").fetchone()
    assert row["status"] == "failed"
    assert row["lease_owner"] is None
    assert row["lease_expires_at"] is None
    assert recover_interrupted_runs() == 0
