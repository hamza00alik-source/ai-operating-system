import opencompany_core.product_rd_coordinator as coordinator_module
from opencompany_core.persistence import SQLiteStore
from opencompany_core.product_rd import ProductRDRepository


def _complete(repo, workflow_id, stage):
    return repo.complete_stage(
        workflow_id, stage,
        output=f"Approved internal output for {stage}",
        evidence=[f"Evidence for {stage}"],
        artifact_refs=[f"internal:{stage}"],
    )


def test_background_coordinator_generates_outpost_and_runs_qa_locally(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "coordinator.sqlite3")
    repo = ProductRDRepository(store._connection, store._lock)
    try:
        workflow = repo.create(
            title="OUTPOST Sci-Fi Survival UI Icon Pack",
            brief="Create an original downloadable SVG prototype.",
            business_id="digital-products",
        )
        for stage in ("opportunity_brief", "product_specification", "production_plan"):
            workflow = _complete(repo, workflow["id"], stage)

        monkeypatch.setattr(
            coordinator_module,
            "generate_outpost_pack",
            lambda workflow_id, root: {
                "artifacts": [{
                    "name": "package.zip", "download_url": f"/product-rd/workflows/{workflow_id}/artifacts/package.zip",
                    "sha256": "0" * 64, "size_bytes": 128,
                }],
                "qa": {
                    "passed_checks": ["archive CRC", "manifest hash"],
                    "failed_checks": [],
                    "untested_claims": ["visual quality", "engine compatibility"],
                },
            },
        )
        coordinator = coordinator_module.ProductRDCoordinator(store, artifact_root=tmp_path / "artifacts")
        result = coordinator.run_once()

        updated = repo.get(workflow["id"])
        assert result["pilot_packs_generated"] == 1
        assert updated["stages"][3]["status"] == "completed"
        assert updated["stages"][4]["status"] == "completed"
        assert updated["stages"][5]["status"] == "in_progress"
        assert updated["stages"][5]["key"] == "human_preview"
        assert store.verify_audit_chain()
    finally:
        store.close()


def test_background_coordinator_does_not_auto_approve_or_queue_drafts(tmp_path):
    store = SQLiteStore(tmp_path / "coordinator-drafts.sqlite3")
    repo = ProductRDRepository(store._connection, store._lock)
    try:
        workflow = repo.create(
            title="Research-first product",
            brief="An internal workflow with no active manager profile.",
            business_id="digital-products",
        )
        coordinator = coordinator_module.ProductRDCoordinator(store)
        result = coordinator.run_once()
        updated = repo.get(workflow["id"])

        assert result["work_items_drafted"] == 0
        assert updated["stages"][0]["work_item_id"] is None
        assert store.list_work_items(business_id="digital-products", limit=10) == ()
    finally:
        store.close()


def test_auto_manager_proposal_is_opt_in_and_idempotent(monkeypatch):
    from types import SimpleNamespace
    from uuid import uuid4
    from opencompany_core.domain import AgentState, TaskState

    parent_id = uuid4()
    manager_id = uuid4()
    item = SimpleNamespace(
        id=parent_id, title="Market opportunity brief",
        objective="Prepare an evidence-based opportunity brief.",
        department="intelligence-research", business_id="digital-products",
        state=TaskState.DRAFT, assigned_agent_id=None,
    )
    manager = SimpleNamespace(
        id=manager_id, role_key="market_intelligence_analyst",
        department="intelligence-research", team_key="management",
        state=AgentState.ACTIVE,
    )
    class Store:
        def get_work_item(self, item_id):
            return item
        def list_agents(self, limit=1000):
            return [manager]
    class Delegations:
        def __init__(self):
            self.proposals = []
        def list_for_parent(self, item_id):
            return list(self.proposals)
        def create_proposal(self, **kwargs):
            self.proposals.append(kwargs)
            return {"id": "proposal-1", "status": "draft"}
    plan = SimpleNamespace(
        mode=SimpleNamespace(value="manager_direct"),
        manager_role_key="market_intelligence_analyst",
        manager_title="Market Intelligence Analyst", specialists=(),
        selected_team_key=None,
    )
    recommendation = SimpleNamespace(
        plan=plan, required_capabilities=("market_research",),
        rationale="The manager can complete this work directly.",
        provider="unorouter", model="free-model",
    )
    monkeypatch.setattr(coordinator_module, "recommend_department_plan",
                        lambda *args, **kwargs: recommendation)
    coordinator = object.__new__(coordinator_module.ProductRDCoordinator)
    class Gateway:
        def eligible_providers(self, request_budget_usd):
            return ["unorouter-free"]
    coordinator.store = Store()
    coordinator.delegations = Delegations()
    coordinator.gateway = Gateway()
    coordinator.auto_manager_proposals_enabled = False
    workflow = {"id": "workflow-1", "business_id": "digital-products"}
    stage = {"key": "opportunity_brief", "work_item_id": str(parent_id)}

    assert coordinator._prepare_manager_proposal(workflow, stage) is False
    assert coordinator.delegations.proposals == []

    coordinator.auto_manager_proposals_enabled = True
    assert coordinator._prepare_manager_proposal(workflow, stage) is True
    assert len(coordinator.delegations.proposals) == 1
    proposal = coordinator.delegations.proposals[0]
    assert proposal["manager_agent_id"] == manager_id
    assert proposal["children"][0]["assigned_agent_id"] == str(manager_id)
    # A second tick sees the existing draft and does not call the planner again.
    assert coordinator._prepare_manager_proposal(workflow, stage) is False
    assert len(coordinator.delegations.proposals) == 1
