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


def test_specialist_loader_uses_pinned_upstream_revision(monkeypatch):
    from ai_os import agent_runtime

    requested = []

    class FakeResponse:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, limit):
            assert limit == 24000
            return b"# Pinned specialist instructions"

    def fake_urlopen(request, timeout):
        requested.append(request.full_url)
        assert timeout == 12
        return FakeResponse()

    monkeypatch.setattr(agent_runtime.urllib.request, "urlopen", fake_urlopen)
    result = agent_runtime._load_specialist({
        "source_repository": "msitarzewski/agency-agents",
        "source_revision": "b37b5bb33b78f2c1d6567d98e25ca818e3259219",
        "source_path": "engineering/engineering-frontend-developer.md",
    })
    assert result == "# Pinned specialist instructions"
    assert requested == [
        "https://raw.githubusercontent.com/msitarzewski/agency-agents/"
        "b37b5bb33b78f2c1d6567d98e25ca818e3259219/"
        "engineering/engineering-frontend-developer.md"
    ]


def test_specialist_loader_rejects_unpinned_or_untrusted_source(monkeypatch):
    from ai_os import agent_runtime

    def unexpected_urlopen(*args, **kwargs):
        raise AssertionError("untrusted source must not be fetched")

    monkeypatch.setattr(agent_runtime.urllib.request, "urlopen", unexpected_urlopen)
    base = {
        "source_repository": "msitarzewski/agency-agents",
        "source_revision": "b37b5bb33b78f2c1d6567d98e25ca818e3259219",
        "source_path": "engineering/engineering-frontend-developer.md",
    }
    assert agent_runtime._load_specialist({**base, "source_revision": "main"}) == ""
    assert agent_runtime._load_specialist({**base, "source_repository": "attacker/repo"}) == ""
    assert agent_runtime._load_specialist({**base, "source_path": "../secrets.md"}) == ""
