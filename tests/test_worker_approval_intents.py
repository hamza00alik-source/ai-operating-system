"""Coverage for model-originated, approval-only worker intents."""
from opencompany_core.worker_runner import OpenCompanyWorker


def test_worker_extracts_one_bounded_approval_block_and_cleans_deliverable():
    raw = (
        "Analysis draft.\\n<OPENCOMPANY_APPROVAL_REQUESTS>\\n"
        '[{"action_type":"publish_listing","title":"Publish draft listing",'
        '"description":"Publish only after owner approval."}]'
        "\\n</OPENCOMPANY_APPROVAL_REQUESTS>"
    )
    requests, cleaned = OpenCompanyWorker._extract_approval_requests(raw)
    assert len(requests) == 1
    assert requests[0]["action_type"] == "publish_listing"
    assert "OPENCOMPANY_APPROVAL_REQUESTS" not in cleaned
    assert cleaned == "Analysis draft."


def test_worker_rejects_unknown_fields_and_invalid_action_types():
    unknown = '<OPENCOMPANY_APPROVAL_REQUESTS>[{"action_type":"payment","title":"Pay","description":"x","api_key":"secret"}]</OPENCOMPANY_APPROVAL_REQUESTS>'
    invalid = '<OPENCOMPANY_APPROVAL_REQUESTS>[{"action_type":"run_shell","title":"Run","description":"x"}]</OPENCOMPANY_APPROVAL_REQUESTS>'
    assert OpenCompanyWorker._extract_approval_requests(unknown) == ([], unknown)
    assert OpenCompanyWorker._extract_approval_requests(invalid) == ([], invalid)


def test_worker_rejects_multiple_blocks_and_more_than_five_requests():
    one = '<OPENCOMPANY_APPROVAL_REQUESTS>[]</OPENCOMPANY_APPROVAL_REQUESTS>'
    assert OpenCompanyWorker._extract_approval_requests(one + one) == ([], one + one)
    six = [{"action_type":"other","title":"x","description":"y"} for _ in range(6)]
    import json
    too_many = "<OPENCOMPANY_APPROVAL_REQUESTS>" + json.dumps(six) + "</OPENCOMPANY_APPROVAL_REQUESTS>"
    assert OpenCompanyWorker._extract_approval_requests(too_many) == ([], too_many)


def test_worker_sends_parsed_intents_to_server_side_sink_with_trusted_identity(tmp_path):
    from uuid import uuid4
    from opencompany_core.domain import AgentProfile, AgentState, TaskState, WorkItem
    from opencompany_core.execution import AgentDeliverable
    from opencompany_core.persistence import SQLiteStore
    from opencompany_core.worker_queue import DurableWorkerQueue

    agent_id = uuid4()
    item = WorkItem(
        id=uuid4(), title="Prepare listing", objective="Prepare a listing draft",
        department="revenue-partnerships", state=TaskState.IN_PROGRESS,
        assigned_agent_id=agent_id, business_id="digital-products",
    )
    store = SQLiteStore(tmp_path / "core.sqlite3")
    store.save_work_item(item)
    store.save_agent(AgentProfile(
        id=agent_id, name="Marketplace Specialist", department="revenue-partnerships",
        purpose="Prepare marketplace work", capabilities=("marketplace_research",),
        state=AgentState.ACTIVE, role_key="marketplace_operations_analyst",
        team_key="management",
    ))
    queue = DurableWorkerQueue(tmp_path / "queue.sqlite3")
    queue.enqueue(item.id, agent_id, {})
    model_output = (
        "Listing research draft.\\n<OPENCOMPANY_APPROVAL_REQUESTS>"
        '[{"action_type":"publish_listing","title":"Publish listing",'
        '"description":"Publish after owner approval."}]'
        "</OPENCOMPANY_APPROVAL_REQUESTS>"
    )

    class Executor:
        def execute(self, role_key, work_item, **kwargs):
            return AgentDeliverable(
                id=uuid4(), work_item_id=work_item.id, role_key=role_key,
                content=model_output, provider="fake", model="deterministic", cost_usd=0.0,
            )

    class Sink:
        def save(self, deliverable):
            pass

    submitted = []
    worker = OpenCompanyWorker(
        queue, store, Executor(), Sink(),
        approval_request_sink=lambda trusted_agent_id, trusted_item, requests:
            submitted.append((trusted_agent_id, trusted_item.id, requests)),
    )
    assert worker.run_once(agent_id, "marketplace_operations_analyst") == "completed_review_required"
    assert len(submitted) == 1
    assert submitted[0][0] == agent_id
    assert submitted[0][1] == item.id
    assert submitted[0][2][0]["action_type"] == "publish_listing"
    assert store.list_deliverables(item.id)[0]["content"] == "Listing research draft."
    queue.close()
    store.close()
