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



def test_worker_reuses_saved_specialist_output_and_only_calls_incomplete_stages(monkeypatch, tmp_path):
    from ai_os import agent_runtime
    from ai_os.agent_runtime import _now
    from ai_os.db import connect, initialize_database

    monkeypatch.setenv("AI_OS_ENV", "development")
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'resume-execution.db'}")
    initialize_database()

    with connect() as db:
        db.execute(
            "INSERT INTO tasks(id,title,description,department,status,created_at) VALUES(?,?,?,?,?,?)",
            ("task-resume", "Research downloadable PC gaming utilities", "", "research", "partial", _now()),
        )
        db.execute(
            """INSERT INTO agent_runs
            (id,task_id,status,assigned_agent_id,specialist_output,created_at,finished_at,error)
            VALUES(?,?,?,?,?,?,?,?)""",
            ("run-resume", "task-resume", "queued", "research/research-synthesist",
             "Previously saved specialist report", _now(), _now(), None),
        )
        db.execute(
            """INSERT INTO agent_run_steps
            (run_id,sequence_no,role,agent_id,agent_name,status,input_summary,output,created_at,finished_at)
            VALUES(?,?,?,?,?,'completed',?,?,?,?)""",
            ("run-resume", 1, "Lead specialist", "research/research-synthesist",
             "Research Synthesist", "Research task", "Previously saved specialist report", _now(), _now()),
        )

    calls = []

    def fake_generate(prompt, preferred_provider=None):
        calls.append({"prompt": prompt, "preferred_provider": preferred_provider})
        return {
            "response": f"Mocked stage result {len(calls)}",
            "provider": "mock-free-provider",
            "model": "mock-model",
            "usage": {},
            "latency_ms": 1,
            "fallback_used": False,
        }

    monkeypatch.setattr(agent_runtime, "generate_with_fallback", fake_generate)
    monkeypatch.setattr(agent_runtime, "_load_specialist", lambda agent: "")
    monkeypatch.setattr(agent_runtime, "retrieve_memories", lambda *args, **kwargs: [])
    monkeypatch.setattr(agent_runtime, "research_context", lambda *args, **kwargs: "")
    monkeypatch.setattr(agent_runtime, "record_experience", lambda *args, **kwargs: "mock-experience")

    assert agent_runtime.run_pending_once() is True

    with connect() as db:
        run = db.execute("SELECT * FROM agent_runs WHERE id='run-resume'").fetchone()
        steps = db.execute(
            "SELECT sequence_no,status,output FROM agent_run_steps WHERE run_id='run-resume' ORDER BY sequence_no"
        ).fetchall()

    assert run["status"] == "completed"
    assert run["specialist_output"] == "Previously saved specialist report"
    assert len(calls) == 2  # collaborator and CEO only; the specialist is reused
    assert all(call["preferred_provider"] == "unorouter" for call in calls)
    assert "Previously saved specialist report" in calls[0]["prompt"]
    assert [step["sequence_no"] for step in steps] == [1, 2, 3]
    assert all(step["status"] == "completed" for step in steps)
    assert steps[0]["output"] == "Previously saved specialist report"
    assert __import__("json").loads(run["usage_json"])["model_calls"] == 2
