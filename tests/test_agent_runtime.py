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



def test_general_market_research_routes_to_opencompany_research_role():
    from ai_os.agent_runtime import _select_specialist, _load_opencompany_catalogue

    catalogue = _load_opencompany_catalogue()
    selected = _select_specialist(
        {"title": "Prepare a global market research brief on downloadable PC gaming utilities",
         "description": "", "department": "general"},
        catalogue,
    )
    assert selected["department"] == "intelligence-research"
    assert selected["id"] == "market_demand_researcher"


def test_company_department_routes_to_opencompany_customer_operations_role():
    from ai_os.agent_runtime import _select_specialist, _load_opencompany_catalogue

    selected = _select_specialist(
        {"title": "Prepare a customer response workflow", "description": "", "department": "customer-support"},
        _load_opencompany_catalogue(),
    )
    assert selected["department"] == "customer-operations"
    assert selected["id"] == "customer_support_analyst"


def test_execution_catalogue_is_opencompany_owned_and_contains_511_roles():
    from ai_os.agent_runtime import _load_opencompany_catalogue

    catalogue = _load_opencompany_catalogue()
    assert len(catalogue["agents"]) == 511
    assert all("source_path" not in role and "source_url" not in role for role in catalogue["agents"])
    assert {role["department"] for role in catalogue["agents"]} >= {
        "intelligence-research", "product-innovation", "engineering",
        "design-creative", "marketing-growth", "sales-marketplace",
        "customer-operations", "finance-operations", "legal-compliance",
        "quality-workforce",
    }


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

def test_specialist_role_briefs_are_opencompany_owned_and_local():
    from ai_os.agent_runtime import _load_specialist

    brief = _load_specialist({
        "id": "research/research-synthesist",
        "name": "Research Synthesist",
        "department": "research",
        "source_path": "ignored/third-party-prompt.md",
    })

    assert "OpenCompany's Research Synthesist" in brief
    assert "separate evidence from inference" in brief
    assert "never fetch third-party prompts" not in brief
    assert "request owner approval" in brief


def test_unknown_specialist_department_gets_safe_local_brief():
    from ai_os.agent_runtime import _load_specialist

    brief = _load_specialist({"name": "Operations Analyst", "department": "operations"})

    assert "OpenCompany's Operations Analyst" in brief
    assert "sound professional practice" in brief
    assert "You have no authority to spend money" in brief

def test_execution_runtime_has_no_legacy_external_workforce_manifests():
    from pathlib import Path

    repository_root = Path(__file__).resolve().parents[1]
    assert not (repository_root / "data" / "agency_agents_manifest.json").exists()
    assert not (repository_root / "data" / "company_departments.json").exists()

def test_all_ten_departments_have_five_original_named_specialist_templates():
    from ai_os.agent_runtime import _load_opencompany_catalogue

    catalogue = _load_opencompany_catalogue()
    department_ids = {
        "intelligence-research", "product-innovation", "engineering",
        "design-creative", "marketing-growth", "sales-marketplace",
        "customer-operations", "finance-operations", "legal-compliance",
        "quality-workforce",
    }
    for department in department_ids:
        team_key = department + "__team_01"
        first_team = [
            role for role in catalogue["agents"]
            if role.get("department") == department and role.get("team_key") == team_key
        ]
        assert len(first_team) == 5
        assert all("Team 1 Specialist" not in role["name"] for role in first_team)
        assert len({role["id"] for role in first_team}) == 5

def test_every_opencompany_department_receives_specific_local_role_guidance():
    from ai_os.agent_runtime import _load_specialist

    departments = [
        "intelligence-research", "product-innovation", "engineering",
        "design-creative", "marketing-growth", "sales-marketplace",
        "customer-operations", "finance-operations", "legal-compliance",
        "quality-workforce",
    ]
    for department in departments:
        brief = _load_specialist({"name": "Department Specialist", "department": department})
        assert "ROLE FOCUS:" in brief
        assert "sound professional practice for the assigned function" not in brief
        assert "request owner approval" in brief
