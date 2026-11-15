"""Static checks for the owner-facing Product & R&D proposal review UI."""

from opencompany_app.product_rd_ui import PRODUCT_RD_JS


def test_manager_proposal_review_exposes_reasoning_and_child_task_details():
    assert "Manager rationale" in PRODUCT_RD_JS
    assert "Required capabilities" in PRODUCT_RD_JS
    assert "Proposed work breakdown" in PRODUCT_RD_JS
    assert "Approval will create READY delegation tasks" in PRODUCT_RD_JS
    assert "No tasks have been approved or queued" in PRODUCT_RD_JS
