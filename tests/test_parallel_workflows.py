import pytest

from ai_os.workflows import create_workflow, finish_workflow_task, get_workflow
from ai_os.db import connect


def test_parallel_company_cycle_releases_independent_branches(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'parallel-cycle.db'}")
    workflow = create_workflow("parallel-company-operating-cycle", business_id="digital-products")
    assert workflow["steps"][0]["status"] == "queued"
    assert all(step["status"] == "blocked" for step in workflow["steps"][1:])
    with connect() as db:
        queued = db.execute("SELECT COUNT(*) AS n FROM agent_runs WHERE task_id IN (?, ?, ?)",
            tuple(step["task_id"] for step in workflow["steps"][:3])).fetchone()["n"]
    assert queued == 1

    finish_workflow_task(workflow["steps"][0]["task_id"], True, "objective")
    finish_workflow_task(workflow["steps"][1]["task_id"], True, "research")
    finish_workflow_task(workflow["steps"][2]["task_id"], True, "offer")

    refreshed = get_workflow(workflow["id"])
    # Design, engineering and compliance become runnable together.
    assert [refreshed["steps"][i]["status"] for i in (3, 4, 5)] == ["queued"] * 3
    with connect() as db:
        queued_runs = db.execute("SELECT COUNT(*) AS n FROM agent_runs WHERE task_id IN (?, ?, ?)",
            tuple(step["task_id"] for step in refreshed["steps"][3:6])).fetchone()["n"]
    assert queued_runs == 3


def test_parallel_downstream_waits_for_all_three_branches(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'parallel-gates.db'}")
    workflow = create_workflow("parallel-company-operating-cycle", business_id="physical-agency")
    for step in workflow["steps"][:3]:
        finish_workflow_task(step["task_id"], True, step["department"] + " output")
    for index in (3, 4):
        finish_workflow_task(workflow["steps"][index]["task_id"], True, "branch output")
    current = get_workflow(workflow["id"])
    assert current["steps"][6]["status"] == "blocked"
    finish_workflow_task(workflow["steps"][5]["task_id"], True, "last branch output")
    current = get_workflow(workflow["id"])
    assert current["steps"][6]["status"] == "queued"
    assert "design output" in current["steps"][6]["output"] or current["steps"][6]["status"] == "queued"
    with connect() as db:
        description = db.execute("SELECT description FROM tasks WHERE id=?",
                                  (workflow["steps"][6]["task_id"],)).fetchone()["description"]
    assert "design output" in description
    assert "engineering output" not in description or "branch output" in description
    assert "last branch output" in description


def test_parallel_workflow_failure_blocks_workflow_without_releasing_descendants(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'parallel-failure.db'}")
    workflow = create_workflow("parallel-company-operating-cycle", business_id="physical-brand")
    finish_workflow_task(workflow["steps"][0]["task_id"], True, "objective")
    finish_workflow_task(workflow["steps"][1]["task_id"], False, "research failed")
    current = get_workflow(workflow["id"])
    assert current["status"] == "blocked"
    assert current["steps"][2]["status"] == "blocked"
