"""Static boundary tests for authenticated agent approval submission."""

from opencompany_app.routers.external_approvals import router


def test_agent_submission_route_is_separate_from_owner_decision_routes():
    paths = {route.path for route in router.routes}
    assert "/internal/agent-approval-requests" in paths
    assert "/external-approvals/{request_id}/decision" in paths


def test_agent_submission_requires_separate_secret_and_work_item_assignment():
    source = __import__(
        "opencompany_app.routers.external_approvals", fromlist=["__file__"]
    ).__file__
    content = open(source, encoding="utf-8").read()
    assert "OPENCOMPANY_AGENT_APPROVAL_API_KEY" in content
    assert "hmac.compare_digest" in content
    assert "item.assigned_agent_id != agent.id" in content
    assert "item.business_id != payload.business_id" in content
    assert "execution_performed" in content
    service_source = __import__(
        "opencompany_core.external_approval_service", fromlist=["__file__"]
    ).__file__
    service_content = open(service_source, encoding="utf-8").read()
    assert 'actor_type="agent"' in service_content
    assert "external_approval.agent_requested" in service_content
    assert "execution_performed" in service_content


def test_core_agent_approval_recorder_is_idempotent(tmp_path):
    from uuid import uuid4
    from opencompany_core.domain import AgentProfile, AgentState, TaskState, WorkItem
    from opencompany_core.external_approval_service import record_agent_approval_requests
    from opencompany_core.persistence import SQLiteStore

    store = SQLiteStore(tmp_path / "approvals.sqlite3")
    agent_id = uuid4()
    item = WorkItem(
        id=uuid4(), title="Research listing", objective="Prepare a draft listing",
        department="revenue-partnerships", state=TaskState.IN_PROGRESS,
        assigned_agent_id=agent_id, business_id="digital-products",
    )
    agent = AgentProfile(
        id=agent_id, name="Marketplace Specialist", department="revenue-partnerships",
        purpose="Prepare marketplace work", capabilities=("marketplace_research",),
        state=AgentState.ACTIVE, role_key="marketplace_operations_analyst",
        team_key="management",
    )
    store.save_work_item(item)
    store.save_agent(agent)
    requests = [{
        "action_type": "publish_listing", "title": "Publish draft listing",
        "description": "Publish only after owner approval.",
        "target_reference": "draft-123", "estimated_amount_minor": None, "currency": None,
    }]
    first = record_agent_approval_requests(store, agent_id, item, requests)
    second = record_agent_approval_requests(store, agent_id, item, requests)
    assert first == second
    assert store._connection.execute(
        "SELECT COUNT(*) FROM external_action_approvals"
    ).fetchone()[0] == 1
    assert store.audit_event_count() == 1
    assert store.verify_audit_chain()
    store.close()
