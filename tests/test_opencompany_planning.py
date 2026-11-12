from datetime import datetime, timezone
from uuid import uuid4

import pytest

from opencompany_core.domain import ApprovalDecision, ApprovalState, TaskState, WorkItem
from opencompany_core.planning import (
    PlanError, WorkPlan, action_requires_owner_approval, authorize_action,
)


def item(state=TaskState.READY, depends_on=()):
    return WorkItem(uuid4(), "Work item", "Complete a defined business outcome",
                    "operations", state=state, depends_on=depends_on)


def test_plan_rejects_unknown_dependency():
    task = item(depends_on=(uuid4(),))
    with pytest.raises(PlanError, match="unknown dependencies"):
        WorkPlan((task,))


def test_plan_rejects_dependency_cycle():
    first_id, second_id = uuid4(), uuid4()
    first = WorkItem(first_id, "First", "First objective", "ops",
                     depends_on=(second_id,))
    second = WorkItem(second_id, "Second", "Second objective", "ops",
                      depends_on=(first_id,))
    with pytest.raises(PlanError, match="cycle"):
        WorkPlan((first, second))


def test_ready_items_wait_for_all_prerequisites():
    prerequisite = item(state=TaskState.IN_PROGRESS)
    dependent = item(depends_on=(prerequisite.id,))
    plan = WorkPlan((prerequisite, dependent))
    assert plan.ready_items() == ()
    assert plan.blocked_items() == (dependent,)


def test_dependent_item_becomes_eligible_when_prerequisite_completes():
    prerequisite = item(state=TaskState.COMPLETED)
    dependent = item(depends_on=(prerequisite.id,))
    plan = WorkPlan((prerequisite, dependent))
    assert plan.ready_items() == (dependent,)
    assert plan.blocked_items() == ()


def test_dependency_chain_is_dependency_first():
    root = item(state=TaskState.COMPLETED)
    middle = item(state=TaskState.COMPLETED, depends_on=(root.id,))
    leaf = item(depends_on=(middle.id,))
    plan = WorkPlan((leaf, middle, root))
    assert plan.dependency_chain(leaf.id) == (root.id, middle.id)


def test_unknown_item_dependency_chain_fails():
    with pytest.raises(PlanError, match="does not exist"):
        WorkPlan(()).dependency_chain(uuid4())


@pytest.mark.parametrize("action", [
    "publish", "purchase", "pay", "send_customer_message",
    "make_customer_commitment", "change_production", "change_credentials",
    "deploy_production", "delete_customer_data",
])
def test_protected_actions_require_owner_approval(action):
    assert action_requires_owner_approval(action)
    assert not authorize_action(action=action, target_type="listing",
                                target_id="listing-7", approval=None)


def test_non_protected_internal_action_does_not_need_approval():
    assert authorize_action(action="draft_report", target_type="document",
                            target_id="doc-1", approval=None)


def test_approval_must_match_exact_action_and_target():
    approval = ApprovalDecision(
        id=uuid4(), action="publish", target_type="listing", target_id="listing-7",
        requested_by="agent", state=ApprovalState.APPROVED,
        requested_at=datetime.now(timezone.utc),
        decided_at=datetime.now(timezone.utc), decided_by="owner",
    )
    assert authorize_action(action="publish", target_type="listing",
                            target_id="listing-7", approval=approval)
    assert not authorize_action(action="publish", target_type="listing",
                                target_id="listing-8", approval=approval)
    assert not authorize_action(action="purchase", target_type="listing",
                                target_id="listing-7", approval=approval)


def test_approval_by_non_owner_is_not_sufficient():
    approval = ApprovalDecision(
        id=uuid4(), action="publish", target_type="listing", target_id="listing-7",
        requested_by="agent", state=ApprovalState.APPROVED,
        requested_at=datetime.now(timezone.utc),
        decided_at=datetime.now(timezone.utc), decided_by="research-agent",
    )
    assert not authorize_action(action="publish", target_type="listing",
                                target_id="listing-7", approval=approval)


def test_plan_rejects_dependencies_across_business_units():
    dependency_id = uuid4()
    agency_task = WorkItem(
        dependency_id, "Supplier research", "Assess supplier fit",
        "research", business_id="physical-agency",
    )
    digital_task = WorkItem(
        uuid4(), "Digital product launch", "Prepare digital product plan",
        "product", depends_on=(dependency_id,), business_id="digital-products",
    )
    with pytest.raises(PlanError, match="cross business-unit"):
        WorkPlan((agency_task, digital_task))
