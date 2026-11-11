from uuid import uuid4

from opencompany_core.domain import WorkItem
from opencompany_core.manager_orchestration import DelegationMode, plan_department_work


def item(department="intelligence-research"):
    return WorkItem(
        id=uuid4(), title="Assess market opportunity",
        objective="Prepare an evidence-based opportunity assessment",
        department=department,
    )


def test_manager_handles_work_directly_when_its_capabilities_cover_the_request():
    plan = plan_department_work(
        item(),
        ["market_research", "competitor_analysis", "source_verification"],
    )
    assert plan.mode == DelegationMode.MANAGER_DIRECT
    assert plan.manager_role_key == "market_intelligence_analyst"
    assert plan.specialists == ()
    assert plan.assignment_performed is False
    assert plan.execution_started is False


def test_manager_selects_one_coherent_specialist_team_when_needed():
    plan = plan_department_work(item(), ["market", "researcher"], max_specialists=5)
    assert plan.mode == DelegationMode.SPECIALIST_TEAM
    assert plan.manager_role_key == "market_intelligence_analyst"
    assert len(plan.specialists) == 5
    assert len({member.team_key for member in plan.specialists}) == 1
    assert plan.selected_team_key == plan.specialists[0].team_key
    assert sum(member.supporting_member for member in plan.specialists) == 2
    assert all(member.matched_capabilities or member.supporting_member for member in plan.specialists)
    assert plan.assignment_performed is False
    assert plan.execution_started is False


def test_manager_escalates_when_no_specialist_matches_required_capabilities():
    plan = plan_department_work(item(), ["capability-that-does-not-exist"])
    assert plan.mode == DelegationMode.OWNER_REVIEW
    assert plan.specialists == ()
    assert plan.uncovered_capabilities == ("capability-that-does-not-exist",)


def test_manager_team_size_is_bounded():
    import pytest

    with pytest.raises(ValueError, match="between 1 and 50"):
        plan_department_work(item(), ["market"], max_specialists=51)



def test_manager_can_select_multiple_specialist_teams_for_large_work_items():
    plan = plan_department_work(item(), ["intelligence_research"], max_specialists=15)
    assert plan.mode == DelegationMode.SPECIALIST_TEAM
    assert len(plan.specialists) == 15
    team_keys = {member.team_key for member in plan.specialists}
    assert len(team_keys) == 3
    assert len({member.role_key for member in plan.specialists}) == 15
    assert plan.selected_team_key is None
