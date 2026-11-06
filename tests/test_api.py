from fastapi.testclient import TestClient
from ai_os.api import app
from ai_os.identity import issue_agent_token

def test_health():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_runtime_explicitly_disables_paid_and_autonomous_execution():
    with TestClient(app) as client:
        response = client.get("/runtime")
    assert response.status_code == 200
    assert response.json()["paid_api_calls_enabled"] is False
    assert response.json()["autonomous_execution_enabled"] is False
    assert response.json()["external_actions_enabled"] is False

def test_agent_registry_lists_enabled_agents():
    with TestClient(app) as client:
        response = client.get("/agents")
    assert response.status_code == 200
    agents = response.json()
    assert len(agents) >= 280
    assert any(agent["id"] == "product-trend-researcher" for agent in agents)

def test_plan_routes_to_specialist_without_executing():
    with TestClient(app) as client:
        response = client.post("/plans", json={"title": "Research customer demand", "description": "Find evidence of willingness to pay.", "department": "research"})
    assert response.status_code == 201
    plan = response.json()
    assert plan["assigned_agent"]["id"] == "research-synthesist"
    assert plan["execution_enabled"] is False
    assert "No model" in plan["notice"]

def test_plan_rejects_unknown_department():
    with TestClient(app) as client:
        response = client.post("/plans", json={"title": "Unknown", "department": "not-a-team"})
    assert response.status_code == 404

def test_work_packet_is_generated_without_api_call():
    with TestClient(app) as client:
        response = client.post("/work-packets", json={"agent_id": "product-trend-researcher", "task": "Research products customers are buying", "context": "Target international customers."})
    assert response.status_code == 201
    packet = response.json()
    assert packet["execution_mode"] == "manual_free_chat"
    assert packet["model_invoked"] is False
    assert packet["api_called"] is False
    assert "Research products customers are buying" in packet["prompt_text"]
    assert "Do not publish" in packet["prompt_text"]

def test_work_packet_rejects_unknown_agent():
    with TestClient(app) as client:
        response = client.post("/work-packets", json={"agent_id": "missing-agent", "task": "Do work"})
    assert response.status_code == 404

def test_work_packet_rejects_blank_task():
    with TestClient(app) as client:
        response = client.post("/work-packets", json={"agent_id": "product-trend-researcher", "task": "   "})
    assert response.status_code == 422

def test_task_and_approval_flow():
    with TestClient(app) as client:
        task = client.post("/tasks", json={"title":"Research demand","department":"research"})
        assert task.status_code == 201
        approval = client.post("/approvals", json={"task_id": task.json()["id"], "action":"publish_content"})
        assert approval.status_code == 403
        assert "trusted CEO runtime identity" in approval.json()["detail"]

def test_approval_cannot_be_decided_twice():
    with TestClient(app) as client:
        approval = client.post("/approvals", json={"action":"spend_money"})
        assert approval.status_code == 403

def test_caller_cannot_claim_ceo_identity_in_approval_payload():
    with TestClient(app) as client:
        response = client.post("/approvals", json={
            "action": "publish_content",
            "details": "Attempted owner approval",
            "agent_id": "company-orchestrator",
        })
    assert response.status_code == 403

def test_job_queue_generates_packet_locally():
    with TestClient(app) as client:
        queued = client.post("/jobs", json={
            "job_type": "build_work_packet",
            "payload": {"agent_id": "product-trend-researcher", "task": "Research international buying demand", "context": "Find evidence of actual purchases."},
            "idempotency_key": "test-job-packet-001"
        })
        assert queued.status_code == 201
        assert queued.json()["status"] == "queued"
        result = client.post("/worker/run-once")
        assert result.status_code == 200
        assert result.json()["processed"] is True
        assert result.json()["job"]["status"] == "completed"
        assert result.json()["job"]["result"]["api_called"] is False
        assert "Research international buying demand" in result.json()["job"]["result"]["prompt_text"]

def test_job_idempotency_returns_existing_job():
    body = {"job_type": "build_work_packet", "payload": {"agent_id": "product-trend-researcher", "task": "Test idempotency"}, "idempotency_key": "test-job-idempotency-001"}
    with TestClient(app) as client:
        first = client.post("/jobs", json=body)
        second = client.post("/jobs", json=body)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

def test_job_rejects_unknown_type():
    with TestClient(app) as client:
        response = client.post("/jobs", json={"job_type": "run_shell", "payload": {}})
    assert response.status_code == 422

def test_job_rejects_incomplete_payload():
    with TestClient(app) as client:
        response = client.post("/jobs", json={"job_type": "build_work_packet", "payload": {"task": "Missing agent"}})
    assert response.status_code == 422

def test_owner_token_is_required_when_configured(monkeypatch):
    monkeypatch.setenv("AI_OS_ENV", "development")
    token = "test-owner-token-" + "x" * 40
    monkeypatch.setenv("AI_OS_API_TOKEN", token)
    with TestClient(app) as client:
        denied = client.get("/agents")
        allowed = client.get("/agents", headers={"Authorization": "Bearer " + token})
    assert denied.status_code == 401
    assert allowed.status_code == 200

def test_production_fails_closed_without_owner_token(monkeypatch):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.delenv("AI_OS_API_TOKEN", raising=False)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/agents").status_code == 503

def test_audit_chain_records_requests_and_verifies():
    with TestClient(app) as client:
        assert client.get("/agents").status_code == 200
        verification = client.get("/audit/verify")
        events = client.get("/audit?limit=20")
    assert verification.status_code == 200
    assert verification.json()["valid"] is True
    assert verification.json()["checked_events"] >= 2
    assert events.status_code == 200
    assert any(event["resource_id"] == "/agents" for event in events.json()["events"])

def test_ceo_is_single_owner_approval_gateway():
    with TestClient(app) as client:
        specialist = client.post("/governance/evaluate", json={"agent_id": "marketing-content-creator", "action": "publish_content"})
        ceo = client.post("/governance/evaluate", json={"agent_id": "company-orchestrator", "action": "publish_content"})
    assert specialist.status_code == 200
    assert specialist.json()["decision"] == "escalate_to_ceo"
    assert specialist.json()["allowed"] is False
    assert specialist.json()["accountable_agent_id"] == "company-orchestrator"
    assert ceo.status_code == 200
    assert ceo.json()["decision"] == "requires_owner_approval"
    assert ceo.json()["owner_approval_required"] is True

def test_department_agents_can_do_allowlisted_internal_work():
    with TestClient(app) as client:
        response = client.post("/governance/evaluate", json={"agent_id": "product-trend-researcher", "action": "research"})
    assert response.status_code == 200
    assert response.json()["decision"] == "allowed_internal"
    assert response.json()["allowed"] is True
    assert response.json()["owner_approval_required"] is False

def test_unknown_actions_fail_closed():
    with TestClient(app) as client:
        response = client.post("/governance/evaluate", json={"agent_id": "engineering-frontend-developer", "action": "run_unclassified_tool"})
    assert response.status_code == 200
    assert response.json()["decision"] == "blocked_unknown_action"
    assert response.json()["allowed"] is False

def test_approval_inbox_rejects_actions_outside_owner_approval_allowlist():
    with TestClient(app) as client:
        response = client.post("/approvals", json={"action": "run_unclassified_tool"})
    assert response.status_code == 403

def test_full_agency_agents_library_is_loaded():
    with TestClient(app) as client:
        response = client.get("/agents")
    assert response.status_code == 200
    agents = response.json()
    assert len(agents) >= 280
    assert any(agent["id"] == "agents-orchestrator" for agent in agents)
    assert any(agent["id"] == "marketing-tiktok-strategist" for agent in agents)
    assert any(agent["id"] == "engineering-backend-architect" for agent in agents)
    assert all(agent["enabled"] for agent in agents)

def test_agent_profile_endpoint_returns_source_instructions():
    with TestClient(app) as client:
        response = client.get("/agents/marketing-content-creator/profile")
    assert response.status_code == 200
    assert "Identity & Role Definition" in response.json()["profile_markdown"]
    assert response.json()["profile_path"] == "marketing/marketing-content-creator.md"

def test_work_packet_includes_full_profile_and_ceo_reporting_rule():
    with TestClient(app) as client:
        response = client.post("/work-packets", json={"agent_id": "marketing-content-creator", "task": "Draft a product launch content plan"})
    assert response.status_code == 201
    prompt = response.json()["prompt_text"]
    assert "FULL SPECIALIST PROFILE" in prompt
    assert "Identity & Role Definition" in prompt
    assert "Report progress, findings, blockers, and recommendations to the CEO Agent" in prompt
    assert "Never contact the owner directly" in prompt

def test_all_agency_agents_runbooks_are_available_and_resolve_agents():
    with TestClient(app) as client:
        response = client.get("/runbooks")
        assert response.status_code == 200
        runbooks = response.json()["runbooks"]
        assert len(runbooks) >= 4
        startup = next(item for item in runbooks if item["slug"] == "startup-mvp")
        assert any("agents-orchestrator" in group["agents"] for group in startup["roster"])
        assert client.get("/runbooks/incident-response").status_code == 200

def _agent_report_headers(agent_id: str, run_id: str):
    return {
        "X-AI-Agent-Token": issue_agent_token(
            agent_id,
            run_id=run_id,
            capabilities=["step.report"],
        )
    }

def _company_run_payload():
    return {
        "title": "Validate a product opportunity",
        "description": "CEO coordinates research then strategy.",
        "steps": [
            {"step_key": "research", "agent_id": "product-trend-researcher", "task": "Research current buyer demand"},
            {"step_key": "strategy", "agent_id": "business-strategist", "task": "Recommend a product", "depends_on": ["research"]}
        ]
    }

def test_company_run_persists_and_dispatches_only_ready_steps(monkeypatch):
    monkeypatch.setenv("AI_OS_AGENT_SIGNING_KEY", "test-signing-key-" + "x" * 40)
    with TestClient(app) as client:
        created = client.post("/company-runs", json=_company_run_payload())
        assert created.status_code == 201, created.text
        run = created.json()
        assert run["status"] == "queued"
        assert run["accountable_agent_id"] == "company-orchestrator"
        assert len(run["steps"]) == 2
        blocked = client.post(f"/company-runs/{run['id']}/steps/strategy/dispatch")
        assert blocked.status_code == 409
        first = client.post(f"/company-runs/{run['id']}/steps/research/dispatch")
        assert first.status_code == 200
        assert first.json()["status"] == "assigned"
        assert first.json()["work_packet"]["api_called"] is False
        report = client.post(f"/company-runs/{run['id']}/steps/research/report", json={
            "status": "completed", "summary": "Found verified demand signals.",
            "evidence": ["https://example.com/source"]
        }, headers=_agent_report_headers("product-trend-researcher", run["id"]))
        assert report.status_code == 200
        second = client.post(f"/company-runs/{run['id']}/steps/strategy/dispatch")
        assert second.status_code == 200
        assert "CEO Agent" in second.json()["work_packet"]["prompt_text"]
        report2 = client.post(f"/company-runs/{run['id']}/steps/strategy/report", json={
            "status": "completed", "summary": "Opportunity recommendation ready."
        }, headers=_agent_report_headers("business-strategist", run["id"]))
        assert report2.status_code == 200
        final = client.get(f"/company-runs/{run['id']}")
        assert final.status_code == 200
        assert final.json()["status"] == "completed"

def test_company_run_rejects_cycles_and_unknown_specialists():
    with TestClient(app) as client:
        cyclic = _company_run_payload()
        cyclic["steps"][0]["depends_on"] = ["strategy"]
        assert client.post("/company-runs", json=cyclic).status_code == 422
        unknown = _company_run_payload()
        unknown["steps"][0]["agent_id"] = "not-a-real-agent"
        assert client.post("/company-runs", json=unknown).status_code == 422

def test_company_run_report_requires_dispatched_step_without_burning_token(monkeypatch):
    monkeypatch.setenv("AI_OS_AGENT_SIGNING_KEY", "test-signing-key-" + "x" * 40)
    with TestClient(app) as client:
        created = client.post("/company-runs", json=_company_run_payload()).json()
        headers = _agent_report_headers("product-trend-researcher", created["id"])
        body = {"status": "completed", "summary": "Cannot report before assignment."}
        early = client.post(f"/company-runs/{created['id']}/steps/research/report", json=body, headers=headers)
        assert early.status_code == 409
        dispatched = client.post(f"/company-runs/{created['id']}/steps/research/dispatch")
        assert dispatched.status_code == 200
        accepted = client.post(f"/company-runs/{created['id']}/steps/research/report", json=body, headers=headers)
        assert accepted.status_code == 200


def test_company_step_report_rejects_wrong_agent_and_replayed_token(monkeypatch):
    monkeypatch.setenv("AI_OS_AGENT_SIGNING_KEY", "test-signing-key-" + "x" * 40)
    with TestClient(app) as client:
        created = client.post("/company-runs", json=_company_run_payload()).json()
        run_id = created["id"]
        client.post(f"/company-runs/{run_id}/steps/research/dispatch")
        wrong_agent = _agent_report_headers("business-strategist", run_id)
        body = {"status": "completed", "summary": "Spoofed report"}
        denied = client.post(f"/company-runs/{run_id}/steps/research/report", json=body, headers=wrong_agent)
        assert denied.status_code == 403
        valid_headers = _agent_report_headers("product-trend-researcher", run_id)
        accepted = client.post(f"/company-runs/{run_id}/steps/research/report", json=body, headers=valid_headers)
        assert accepted.status_code == 200
        replay = client.post(f"/company-runs/{run_id}/steps/research/report", json=body, headers=valid_headers)
        assert replay.status_code == 409

def test_company_step_report_rejects_token_for_another_run(monkeypatch):
    monkeypatch.setenv("AI_OS_AGENT_SIGNING_KEY", "test-signing-key-" + "x" * 40)
    with TestClient(app) as client:
        first = client.post("/company-runs", json=_company_run_payload()).json()
        second = client.post("/company-runs", json=_company_run_payload()).json()
        client.post(f"/company-runs/{first['id']}/steps/research/dispatch")
        headers = _agent_report_headers("product-trend-researcher", second["id"])
        response = client.post(f"/company-runs/{first['id']}/steps/research/report", json={
            "status": "completed", "summary": "Wrong run"
        }, headers=headers)
        assert response.status_code == 403


def test_ceo_brain_creates_persisted_company_plan():
    with TestClient(app) as client:
        response = client.post("/ceo/plan", json={
            "objective": "Launch an international digital product business with a WordPress store and organic marketing",
            "context": "Zero budget. No cold outreach."
        })
        assert response.status_code == 201, response.text
        plan = response.json()
        assert plan["planning_mode"] == "deterministic_rules_v1"
        assert plan["accountable_agent_id"] == "company-orchestrator"
        assert plan["run"]["accountable_agent_id"] == "company-orchestrator"
        assert len(plan["run"]["steps"]) >= 10
        keys = {step["step_key"] for step in plan["run"]["steps"]}
        assert {"discover", "validate_market", "define_offer", "growth_plan", "content_drafts", "quality_gate", "build_solution"} <= keys
        assert any(item["agent_id"] == "engineering-backend-architect" for item in plan["decision_log"])
        assert all(step["status"] == "pending" for step in plan["run"]["steps"])
        assert any("no AI model was invoked" in item for item in plan["limitations"])

def test_ceo_brain_plan_is_retrievable():
    with TestClient(app) as client:
        created = client.post("/ceo/plan", json={"objective": "Build an organic content business for international customers"})
        assert created.status_code == 201
        run_id = created.json()["run_id"]
        fetched = client.get(f"/ceo/plans/{run_id}")
    assert fetched.status_code == 200
    assert fetched.json()["run_id"] == run_id
    assert fetched.json()["planning_mode"] == "deterministic_rules_v1"

def test_ceo_brain_adds_design_finance_and_security_workstreams_when_relevant():
    with TestClient(app) as client:
        response = client.post("/ceo/plan", json={
            "objective": "Create a secure 3D character asset business with pricing, payments, and brand design"
        })
    assert response.status_code == 201, response.text
    keys = {step["step_key"] for step in response.json()["run"]["steps"]}
    assert {"design_direction", "unit_economics", "security_review"} <= keys

def test_ceo_brain_rejects_blank_or_too_short_objective():
    with TestClient(app) as client:
        response = client.post("/ceo/plan", json={"objective": "   "})
    assert response.status_code == 422



def test_owner_api_token_cannot_impersonate_ceo_for_approval_request(monkeypatch):
    token = "test-owner-token-" + "x" * 40
    monkeypatch.setenv("AI_OS_ENV", "development")
    monkeypatch.setenv("AI_OS_API_TOKEN", token)
    with TestClient(app) as client:
        response = client.post(
            "/approvals",
            json={"action": "publish_product", "details": "Attempt to bypass CEO identity"},
            headers={"Authorization": "Bearer " + token},
        )
    assert response.status_code == 403


def test_owner_dashboard_shell_is_available_but_data_api_remains_protected(monkeypatch):
    token = "test-owner-token-" + "x" * 40
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_API_TOKEN", token)
    with TestClient(app) as client:
        page = client.get("/dashboard")
        denied = client.get("/agents")
        allowed = client.get("/agents", headers={"Authorization": "Bearer " + token})
    assert page.status_code == 200
    assert "Owner dashboard" in page.text
    assert "Agent directory" in page.text
    assert denied.status_code == 401
    assert allowed.status_code == 200


def test_dashboard_is_backed_by_persisted_run_and_job_api():
    with TestClient(app) as client:
        assert client.get("/company-runs").status_code == 200
        assert client.get("/jobs").status_code == 200
        assert client.get("/runtime").json()["external_actions_enabled"] is False


def test_owner_dashboard_includes_agent_progress_and_refresh_features():
    with TestClient(app) as client:
        page = client.get("/dashboard")
        model_status = client.get("/models/status")
    assert page.status_code == 200
    assert 'api("/agents")' in page.text
    assert 'api("/company-runs?limit=100")' in page.text
    assert 'api("/jobs?limit=100")' in page.text
    assert 'api("/approvals")' in page.text
    assert 'api("/knowledge?status=candidate&limit=30")' in page.text
    assert "Research review inbox" in page.text
    assert "reviewKnowledge" in page.text
    assert 'api("/audit?limit=30")' in page.text
    assert 'api("/models/status")' in page.text
    assert "Queued work" in page.text
    assert "Last recorded activity" in page.text
    assert "steps complete" in page.text
    assert "setInterval" in page.text
    assert model_status.status_code == 200
    assert model_status.json()["makes_network_request"] is False



def test_evaluation_history_endpoint_requires_owner_token_when_configured(monkeypatch):
    token = "test-owner-token-" + "x" * 40
    monkeypatch.setenv("AI_OS_ENV", "development")
    monkeypatch.setenv("AI_OS_API_TOKEN", token)
    with TestClient(app) as client:
        denied = client.get("/evaluations")
        allowed = client.get("/evaluations?agent_id=agent-that-does-not-exist", headers={"Authorization": "Bearer " + token})
    assert denied.status_code == 401
    assert allowed.status_code == 200
    assert allowed.json()["summary"]["total"] == 0
    assert allowed.json()["evaluations"] == []


def test_owner_dashboard_displays_evaluation_history():
    with TestClient(app) as client:
        page = client.get("/dashboard")
    assert page.status_code == 200
    assert "Agent quality & learning" in page.text
    assert 'api("/evaluations?limit=30")' in page.text
    assert "evaluationSummary" in page.text
    assert "evaluator_version" in page.text
    assert "scores do not verify truth" in page.text



def test_evaluation_trends_endpoint_returns_sample_gated_result():
    with TestClient(app) as client:
        response = client.get("/evaluations/trends?agent_id=agent-that-does-not-exist&limit=20")
    assert response.status_code == 200
    assert response.json()["limit"] == 20
    assert response.json()["trends"] == []


def test_owner_dashboard_loads_and_displays_evaluation_trends():
    with TestClient(app) as client:
        page = client.get("/dashboard")
    assert page.status_code == 200
    assert 'api("/evaluations/trends?limit=100")' in page.text
    assert "evaluationTrends" in page.text
    assert "provisional regression" in page.text or "signal.replaceAll" in page.text



def test_ceo_improvement_proposal_draft_and_owner_review_are_audited(tmp_path, monkeypatch):
    from ai_os.db import connect, initialize_database

    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'api-proposals.sqlite3'}")
    initialize_database()
    with connect() as db:
        db.execute(
            "INSERT INTO company_runs (id,title,description,status,created_at,updated_at) "
            "VALUES ('api-proposal-run','API proposal','','running','2026-11-06T00:00:00Z','2026-11-06T00:00:00Z')"
        )
        for index in range(2):
            db.execute(
                """INSERT INTO company_run_steps
                (run_id,step_key,agent_id,task,context,depends_on_json,status,position,created_at,updated_at)
                VALUES ('api-proposal-run',?,'researcher','Task','','[]','completed',?,
                        '2026-11-06T00:00:00Z','2026-11-06T00:00:00Z')""",
                (f"step-{index}", index),
            )
            db.execute(
                """INSERT INTO agent_evaluations
                (id,run_id,step_key,agent_id,evaluator_version,score,passed,
                 critical_failures_json,checks_json,limitations_json,created_at)
                VALUES (?, 'api-proposal-run', ?, 'researcher','1.0.0',75,0,'[]',
                        '[{"key":"completed_has_evidence","passed":false,"weight":15}]',
                        '[]',?)""",
                (f"api-eval-{index}", f"step-{index}", f"2026-11-06T00:00:0{index}Z"),
            )
    with TestClient(app) as client:
        drafted = client.post("/ceo/improvement-proposals/draft")
        assert drafted.status_code == 201, drafted.text
        proposal = drafted.json()["proposals"][0]
        assert proposal["status"] == "candidate"
        reviewed = client.post(
            f"/improvement-proposals/{proposal['id']}/review",
            json={"decision": "approved_for_testing", "note": "Test before any adoption."},
        )
        assert reviewed.status_code == 200
        assert reviewed.json()["status"] == "approved_for_testing"
        assert reviewed.json()["status"] != "adopted"
        assert client.get("/audit/verify").json()["valid"] is True


def test_improvement_proposal_routes_require_owner_token_when_configured(monkeypatch):
    token = "test-owner-token-" + "x" * 40
    monkeypatch.setenv("AI_OS_ENV", "development")
    monkeypatch.setenv("AI_OS_API_TOKEN", token)
    with TestClient(app) as client:
        denied = client.get("/improvement-proposals")
        allowed = client.get("/improvement-proposals", headers={"Authorization": "Bearer " + token})
    assert denied.status_code == 401
    assert allowed.status_code == 200


def test_owner_dashboard_wires_improvement_proposal_review():
    with TestClient(app) as client:
        page = client.get("/dashboard")
    assert page.status_code == 200
    assert "CEO improvement proposals" in page.text
    assert 'api("/improvement-proposals?limit=50")' in page.text
    assert "generateImprovements" in page.text
    assert "Approve for testing" in page.text
    assert "never auto-adopted" in page.text



def _seed_api_improvement_proposal(db_path, monkeypatch, *, status="approved_for_testing"):
    import json
    from ai_os.db import connect, initialize_database

    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{db_path}")
    initialize_database()
    with connect() as db:
        db.execute(
            """INSERT INTO improvement_proposals
            (id,agent_id,title,problem,evidence_json,proposed_change,expected_impact,status,created_at)
            VALUES ('test-api-proposal','researcher','Evidence quality','Repeated failures',?,
                    'Require task-relevant evidence before marking a step completed.',
                    'Improve evidence completeness.',?,'2026-11-06T00:00:00Z')""",
            (json.dumps([{"evaluation_id":"eval-1"},{"evaluation_id":"eval-2"}]), status),
        )


def test_improvement_test_endpoint_records_result_without_adopting(tmp_path, monkeypatch):
    _seed_api_improvement_proposal(tmp_path / "test-api.sqlite3", monkeypatch)
    with TestClient(app) as client:
        response = client.post("/improvement-proposals/test-api-proposal/test")
        proposal = client.get("/improvement-proposals").json()[0]
        history = client.get("/improvement-proposals/test-api-proposal/tests").json()
        audit = client.get("/audit/verify").json()
    assert response.status_code == 201, response.text
    assert response.json()["passed"] is True
    assert proposal["status"] == "approved_for_testing"
    assert len(history) == 1
    assert audit["valid"] is True


def test_improvement_test_endpoint_rejects_unapproved_proposal(tmp_path, monkeypatch):
    _seed_api_improvement_proposal(
        tmp_path / "test-unapproved.sqlite3", monkeypatch, status="candidate"
    )
    with TestClient(app) as client:
        response = client.post("/improvement-proposals/test-api-proposal/test")
    assert response.status_code == 409


def test_improvement_test_routes_require_owner_token_when_configured(tmp_path, monkeypatch):
    token = "test-owner-token-" + "x" * 40
    monkeypatch.setenv("AI_OS_ENV", "development")
    monkeypatch.setenv("AI_OS_API_TOKEN", token)
    _seed_api_improvement_proposal(tmp_path / "test-auth.sqlite3", monkeypatch)
    with TestClient(app) as client:
        denied = client.get("/improvement-proposals/test-api-proposal/tests")
        allowed = client.get(
            "/improvement-proposals/test-api-proposal/tests",
            headers={"Authorization": "Bearer " + token},
        )
    assert denied.status_code == 401
    assert allowed.status_code == 200


def test_owner_dashboard_exposes_static_improvement_test_action():
    with TestClient(app) as client:
        page = client.get("/dashboard")
    assert page.status_code == 200
    assert "Run static safety checks" in page.text
    assert "testImprovement" in page.text
    assert "does not test model behavior or activate the change" in page.text



def test_owner_dashboard_loads_and_displays_static_improvement_test_history():
    with TestClient(app) as client:
        page = client.get("/dashboard")
    assert page.status_code == 200
    assert '"/tests?limit=3"' in page.text
    assert "Latest static test:" in page.text
    assert "PASSED" in page.text and "FAILED" in page.text
