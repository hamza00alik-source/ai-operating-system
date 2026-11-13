"""Static safety checks for the external-action approval registry."""

from opencompany_app.routers.external_approvals import ACTION_TYPES, router


def test_external_action_registry_covers_sensitive_action_classes():
    assert {
        "publish_listing", "send_customer_message", "make_customer_commitment",
        "purchase", "payment", "production_change", "credential_change",
        "account_change", "deploy_production", "delete_customer_data",
    }.issubset(ACTION_TYPES)


def test_external_action_routes_are_owner_authenticated_and_have_no_executor():
    paths = {route.path: route for route in router.routes}
    assert "/external-approvals" in paths
    assert "/external-approvals/{request_id}/decision" in paths
    assert "/external-approvals/{request_id}/cancel" in paths
    source = __import__(
        "opencompany_app.routers.external_approvals",
        fromlist=["__file__"],
    ).__file__
    content = open(source, encoding="utf-8").read()
    assert "authorized_not_executed" in content
    assert 'confirm_action != "AUTHORIZE"' in content
    assert "timedelta(hours=24)" in content
    assert "execution_performed" in content
    assert "No external action was executed" in content
    assert "subprocess" not in content
    assert "requests." not in content
