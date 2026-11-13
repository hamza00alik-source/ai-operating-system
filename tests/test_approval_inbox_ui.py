"""Static checks for the company-wide owner approval inbox."""

from opencompany_app.approval_inbox_ui import APPROVAL_INBOX_HTML, APPROVAL_INBOX_JS


def test_inbox_exposes_supported_owner_decision_categories():
    assert "Manager proposal" in APPROVAL_INBOX_JS
    assert "Deliverable review" in APPROVAL_INBOX_JS
    assert "Human preview" in APPROVAL_INBOX_JS
    assert "CEO review" in APPROVAL_INBOX_JS


def test_manager_proposal_approval_keeps_existing_owner_gate():
    assert "/delegation-proposals/" in APPROVAL_INBOX_JS
    assert "Approval creates READY delegation tasks only" in APPROVAL_INBOX_JS
    assert "clarification or a complete team is required" in APPROVAL_INBOX_JS


def test_deliverable_review_uses_existing_owner_review_endpoint():
    assert '"/work-items/"+entry.id+"/deliverables"' in APPROVAL_INBOX_JS
    assert '"/work-items/"+entry.id+"/review"' in APPROVAL_INBOX_JS
    assert "Approved by owner in the company-wide approval inbox." in APPROVAL_INBOX_JS


def test_external_action_categories_are_explicitly_unwired():
    assert "Not yet connected" in APPROVAL_INBOX_HTML
    assert "does not create or execute those actions" in APPROVAL_INBOX_HTML


def test_inbox_does_not_automatically_approve_or_execute():
    assert "approval-inbox-refresh" in APPROVAL_INBOX_HTML
    assert "Approve manager proposal" in APPROVAL_INBOX_JS
    assert "Open Product & R&D checkpoint" in APPROVAL_INBOX_JS
