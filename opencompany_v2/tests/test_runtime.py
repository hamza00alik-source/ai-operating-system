import sqlite3

import pytest

from opencompany.permissions import Action
from opencompany.queue import ExecutionQueue
from opencompany.runtime import build_skill_worker
from opencompany.skills import Skill, SkillRegistry


@pytest.fixture
def queue():
    db = sqlite3.connect(":memory:", check_same_thread=False)
    db.row_factory = sqlite3.Row
    yield ExecutionQueue(db)
    db.close()


def registry_with_skills():
    registry = SkillRegistry()
    registry.register(
        Skill("market_scan", "Find evidence", "Research public information",
              (Action.RESEARCH.value,), ()),
        lambda payload: {"query": payload["query"], "evidence_count": 3},
    )
    registry.register(
        Skill("publisher", "Publish content", "Publish an approved draft",
              (Action.PUBLISH.value,), (Action.PUBLISH.value,)),
        lambda payload: {"published_id": payload["draft_id"]},
    )
    return registry


def test_runtime_dispatches_registered_research_skill(queue):
    registry = registry_with_skills()
    job_id = queue.enqueue("runtime-research-1", {
        "handler": "research", "input": {"query": "buyer demand"}
    })
    worker = build_skill_worker(
        queue, "worker-1", registry,
        {"research": ("market_scan", "research")},
    )

    result = worker.run_once()

    assert result["status"] == "completed"
    assert queue.get(job_id)["state"] == "completed"
    assert result["result"]["skill_key"] == "market_scan"
    assert result["result"]["output"] == {
        "query": "buyer demand", "evidence_count": 3
    }


def test_runtime_blocks_publish_without_trusted_approval(queue):
    registry = registry_with_skills()
    job_id = queue.enqueue("runtime-publish-1", {
        "handler": "publish",
        "input": {"draft_id": "draft-1", "owner_approved": True},
    })
    worker = build_skill_worker(
        queue, "worker-1", registry,
        {"publish": ("publisher", "publish")},
    )

    result = worker.run_once()

    assert result["status"] == "failed"
    assert "approval required" in result["error"]
    assert queue.get(job_id)["state"] == "queued"


def test_runtime_accepts_only_trusted_approval_resolver(queue):
    registry = registry_with_skills()
    job_id = queue.enqueue("runtime-publish-2", {
        "handler": "publish",
        "input": {"draft_id": "draft-2", "approval_id": "owner-record-42"},
    })
    worker = build_skill_worker(
        queue, "worker-1", registry,
        {"publish": ("publisher", "publish")},
        approval_resolver=lambda skill, action, payload: (
            skill == "publisher" and action == "publish"
            and payload.get("approval_id") == "owner-record-42"
        ),
    )

    result = worker.run_once()

    assert result["status"] == "completed"
    assert queue.get(job_id)["state"] == "completed"
    assert result["result"]["output"] == {"published_id": "draft-2"}


def test_runtime_rejects_malformed_routes(queue):
    with pytest.raises(ValueError, match="route"):
        build_skill_worker(
            queue, "worker-1", registry_with_skills(), {"bad": "market_scan"}
        )
