from uuid import uuid4

from opencompany_core.delegation_records import DelegationRepository


def test_proposal_and_child_tasks_are_durable_and_idempotent(tmp_path):
    database = tmp_path / "core.sqlite3"
    repository = DelegationRepository(database)
    parent = uuid4()
    manager = uuid4()
    child = {
        "assigned_agent_id": str(uuid4()),
        "role_key": "research__source_analyst",
        "team_key": "intelligence-research__team_1",
        "title": "Source Analyst: Market assessment",
        "objective": "Prepare an internal evidence draft.",
    }
    request = {"required_capabilities": ["source_verification"], "max_specialists": 1}
    first = repository.create_proposal(
        parent_work_item_id=parent, request=request, manager_agent_id=manager,
        mode="specialist_team", team_key=child["team_key"], children=[child],
    )
    second = repository.create_proposal(
        parent_work_item_id=parent, request=request, manager_agent_id=manager,
        mode="specialist_team", team_key=child["team_key"], children=[child],
    )
    assert first["id"] == second["id"]
    assert len(first["children"]) == 1
    assert first["children"][0]["state"] == "draft"
    assert first["status"] == "draft"
    assert first["execution_started"] is False
    assert first["queue_entries_created"] is False
    repository.close()

    reopened = DelegationRepository(database)
    saved = reopened.get_proposal(__import__("uuid").UUID(first["id"]))
    assert saved is not None
    assert saved["parent_work_item_id"] == str(parent)
    assert saved["children"][0]["assigned_agent_id"] == child["assigned_agent_id"]
    assert len(reopened.list_for_parent(parent)) == 1
    reopened.close()


def test_different_requests_create_distinct_proposals(tmp_path):
    repository = DelegationRepository(tmp_path / "core.sqlite3")
    parent = uuid4()
    common = {
        "parent_work_item_id": parent, "manager_agent_id": None,
        "mode": "owner_review", "team_key": None, "children": [],
    }
    first = repository.create_proposal(request={"required_capabilities": ["a"]}, **common)
    second = repository.create_proposal(request={"required_capabilities": ["b"]}, **common)
    assert first["id"] != second["id"]
    assert len(repository.list_for_parent(parent)) == 2
    repository.close()
