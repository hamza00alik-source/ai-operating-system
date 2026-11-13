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
    assert 'actor_type="agent"' in content
    assert "external_approval.agent_requested" in content
    assert "execution_performed" in content
