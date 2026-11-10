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


def test_atomic_worker_claim_allows_only_one_process_to_claim_a_run(monkeypatch, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from ai_os.agent_runtime import create_run, _claim_next_run
    from ai_os.db import connect, initialize_database

    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'atomic-claim.db'}")
    initialize_database()
    with connect() as db:
        db.execute(
            "INSERT INTO tasks(id,title,description,department,business_id,status,created_at) VALUES(?,?,?,?,?,?,?)",
            ("claim-task", "Synthetic worker claim", "No external actions.", "research", "core", "queued", "2026-01-01T00:00:00+00:00"),
        )
    create_run("claim-task")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: _claim_next_run(), range(2)))
    claimed = [item for item in results if item is not None]
    assert len(claimed) == 1
    assert claimed[0][0]
    assert claimed[0][1]["id"] == "claim-task"
    with connect() as db:
        assert db.execute("SELECT status FROM agent_runs WHERE task_id='claim-task'").fetchone()["status"] == "running"
        assert db.execute("SELECT status FROM tasks WHERE id='claim-task'").fetchone()["status"] == "running"


def test_worker_loop_stops_cleanly_after_stop_signal(monkeypatch):
    import threading
    from ai_os import agent_runtime

    stop = threading.Event()
    calls = []
    def idle_once():
        calls.append(True)
        stop.set()
        return False

    monkeypatch.setattr(agent_runtime, "run_pending_once", idle_once)
    agent_runtime.worker_loop(stop, poll_seconds=1)
    assert len(calls) == 1


def test_worker_pool_starts_the_configured_number_of_consumers(monkeypatch):
    import threading
    from ai_os import agent_runtime

    stop = threading.Event()
    barrier = threading.Barrier(2)
    thread_ids = []

    def fake_worker_loop(stop_event, poll_seconds):
        thread_ids.append(threading.get_ident())
        barrier.wait(timeout=3)
        stop_event.set()

    monkeypatch.setattr(agent_runtime, "worker_loop", fake_worker_loop)
    agent_runtime.worker_pool(stop, poll_seconds=1, concurrency=2)
    assert len(set(thread_ids)) == 2


def test_worker_pool_clamps_concurrency_to_four(monkeypatch):
    import threading
    from ai_os import agent_runtime

    stop = threading.Event()
    started = []
    barrier = threading.Barrier(4)

    def fake_worker_loop(stop_event, poll_seconds):
        started.append(threading.get_ident())
        barrier.wait(timeout=3)
        stop_event.set()

    monkeypatch.setattr(agent_runtime, "worker_loop", fake_worker_loop)
    agent_runtime.worker_pool(stop, poll_seconds=1, concurrency=99)
    assert len(set(started)) == 4
