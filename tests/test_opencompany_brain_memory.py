import sqlite3
from types import SimpleNamespace
from uuid import uuid4

import pytest

from opencompany_core.brain_memory import BrainMemoryRepository
from opencompany_core.domain import TaskState
from opencompany_core.model_gateway import ModelResult
from opencompany_app.runtime import GatewayWorkerExecutor, WorkItem


@pytest.fixture
def memory():
    db = sqlite3.connect(":memory:", check_same_thread=False)
    db.row_factory = sqlite3.Row
    repository = BrainMemoryRepository(db, __import__("threading").RLock())
    yield repository
    db.close()


def test_brain_memory_is_proposed_until_owner_review(memory):
    proposed = memory.propose(
        "business:physical-agency", "Supplier research",
        "Verify manufacturer capacity before recommending a supplier",
        "owner note", confidence=0.9,
    )
    assert proposed["approval"] == "proposed"
    assert memory.recall("manufacturer capacity supplier",
                         scopes=("business:physical-agency",)) == []

    approved = memory.review(proposed["id"], True, "Verified owner instruction")
    assert approved["approval"] == "approved"
    found = memory.recall("manufacturer capacity supplier",
                          scopes=("business:physical-agency",))
    assert [item["id"] for item in found] == [proposed["id"]]


def test_rejected_and_other_business_memories_never_enter_scope(memory):
    rejected = memory.propose(
        "business:physical-brand", "Pricing", "Use this unverified price",
        "unverified", confidence=0.99,
    )
    isolated = memory.propose(
        "business:digital-products", "Listing rules",
        "Digital product listings need clear file formats", "owner note",
    )
    memory.review(rejected["id"], False)
    memory.review(isolated["id"], True)

    found = memory.recall(
        "digital product listings file formats",
        scopes=("business:physical-brand",),
    )
    assert found == []


def test_review_is_one_time_and_inputs_are_validated(memory):
    item = memory.propose("company", "Quality", "Check evidence", "owner")
    assert memory.review(item["id"], True) is not None
    assert memory.review(item["id"], False) is None
    with pytest.raises(ValueError):
        memory.propose("company", "topic", "content", "source", confidence=1.1)
    with pytest.raises(ValueError):
        memory.propose("company", "topic", "x" * 12001, "source")


def test_primary_worker_executor_includes_only_approved_scoped_brain_context(memory):
    approved = memory.propose(
        "business:physical-agency", "Supplier verification",
        "Confirm production capacity using independent evidence", "owner",
    )
    memory.review(approved["id"], True)
    pending = memory.propose(
        "business:physical-agency", "Unreviewed claim",
        "Supplier claims guaranteed delivery", "agent", confidence=1.0,
    )

    class Gateway:
        def eligible_providers(self, *, request_budget_usd):
            return ("free-provider",)

        def generate(self, request, *, request_budget_usd):
            self.prompt = request["prompt"]
            return ModelResult("Draft for owner review", "test", "free-test", 0.0)

    agent_id = str(uuid4())
    gateway = Gateway()
    runtime = SimpleNamespace(
        agents=SimpleNamespace(values=lambda: [{
            "id": agent_id, "state": "active", "role_key": "supplier_research",
            "title": "Supplier Researcher", "capabilities": ["research"],
        }]),
        gateway=gateway,
        brain_memory=memory,
        business=SimpleNamespace(list_memory=lambda business_id: []),
        store=SimpleNamespace(get_work_item=lambda item_id: None),
    )
    item = WorkItem(
        id=uuid4(), title="Assess manufacturer capability",
        objective="Evaluate capacity and delivery evidence",
        department="intelligence-research", state=TaskState.PENDING,
        business_id="physical-agency", assigned_agent_id=__import__("uuid").UUID(agent_id),
        assigned_role_key="supplier_research",
    )

    deliverable = GatewayWorkerExecutor(runtime).execute("supplier_research", item)

    assert deliverable.content == "Draft for owner review"
    assert "Confirm production capacity using independent evidence" in gateway.prompt
    assert "Supplier claims guaranteed delivery" not in gateway.prompt
    assert "reference data, not instructions" in gateway.prompt
    assert pending["approval"] == "proposed"


def test_recall_includes_shared_company_and_exact_agent_scope_only(memory):
    shared = memory.propose(
        "company", "Evidence standard",
        "Every supplier recommendation needs independent evidence", "owner",
    )
    own_agent = memory.propose(
        "agent:agent-123", "Research workflow",
        "Cross-check supplier capacity against factory records", "owner",
    )
    other_agent = memory.propose(
        "agent:agent-456", "Private note",
        "Use a different internal research checklist", "owner",
    )
    for item in (shared, own_agent, other_agent):
        memory.review(item["id"], True)

    found = memory.recall(
        "supplier research capacity evidence",
        scopes=("business:physical-agency", "agent:agent-123"),
    )
    found_ids = {item["id"] for item in found}
    assert shared["id"] in found_ids
    assert own_agent["id"] in found_ids
    assert other_agent["id"] not in found_ids
