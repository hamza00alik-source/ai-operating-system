import sqlite3

import pytest

from opencompany.brain import Brain
from opencompany.permissions import Action
from opencompany.queue import ExecutionQueue
from opencompany.runtime import build_skill_worker
from opencompany.skills import Skill, SkillRegistry


@pytest.fixture
def db():
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    yield connection
    connection.close()


def test_brain_requires_valid_proposals_and_only_recalls_approved(db):
    brain = Brain(db)
    brain.initialize()
    memory_id = brain.propose(
        "company", "Buyer preferences", "Buyers request clear delivery timelines",
        "owner note", confidence=0.8,
    )
    assert brain.recall("buyer delivery", "company") == []
    assert brain.review(memory_id, True) is True
    results = brain.recall("buyer delivery", "company")
    assert len(results) == 1
    assert results[0]["id"] == memory_id
    assert results[0]["approval"] == "approved"
    with pytest.raises(ValueError):
        brain.propose("", "topic", "content", "source")
    with pytest.raises(ValueError):
        brain.recall("buyer", "company", 0)


def test_brain_recall_is_scoped_to_agent_and_shared_company_memory(db):
    brain = Brain(db)
    brain.initialize()
    private_id = brain.propose(
        "agent:research-1", "Research method", "Compare buyer demand evidence",
        "approved owner input",
    )
    shared_id = brain.propose(
        "company", "Company rule", "Use evidence before recommending suppliers",
        "owner input",
    )
    other_id = brain.propose(
        "agent:sales-2", "Sales notes", "Follow up on quotations",
        "owner input",
    )
    for memory_id in (private_id, shared_id, other_id):
        brain.review(memory_id, True)

    found = brain.recall("buyer evidence supplier", "agent:research-1")

    found_ids = {item["id"] for item in found}
    assert private_id in found_ids
    assert shared_id in found_ids
    assert other_id not in found_ids


def test_worker_receives_brain_context_not_job_supplied_memory(db):
    brain = Brain(db)
    brain.initialize()
    memory_id = brain.propose(
        "company", "Research standard", "Verify claims with primary evidence",
        "owner instruction",
    )
    brain.review(memory_id, True)

    registry = SkillRegistry()
    registry.register(
        Skill("research", "Research", "Research using approved context",
              (Action.RESEARCH.value,), ()),
        lambda payload: {
            "memory_ids": [item["id"] for item in payload["memory_context"]],
            "query": payload["query"],
            "spoofed_context_seen": "memory_context" in payload
                and any(item.get("id") == "fake" for item in payload["memory_context"]),
        },
    )
    queue = ExecutionQueue(db)
    job_id = queue.enqueue("brain-runtime-job", {
        "handler": "research",
        "input": {
            "query": "market scan",
            "memory_query": "research evidence",
            "memory_context": [{"id": "fake", "content": "untrusted"}],
        },
    })
    worker = build_skill_worker(
        queue, "worker-1", registry,
        {"research": ("research", "research")},
        brain=brain,
    )

    result = worker.run_once()

    assert result["status"] == "completed"
    assert queue.get(job_id)["state"] == "completed"
    assert result["result"]["output"]["memory_ids"] == [memory_id]
    assert result["result"]["output"]["spoofed_context_seen"] is False


def test_runtime_without_brain_does_not_add_memory_context(db):
    registry = SkillRegistry()
    registry.register(
        Skill("research", "Research", "Research without memory",
              (Action.RESEARCH.value,), ()),
        lambda payload: {"keys": sorted(payload)},
    )
    queue = ExecutionQueue(db)
    queue.enqueue("no-brain-job", {
        "handler": "research", "input": {"query": "test"}
    })
    worker = build_skill_worker(
        queue, "worker-1", registry,
        {"research": ("research", "research")},
    )
    result = worker.run_once()
    assert result["status"] == "completed"
    assert result["result"]["output"]["keys"] == ["query"]
