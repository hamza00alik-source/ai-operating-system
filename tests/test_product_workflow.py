from opencompany_core.persistence import SQLiteStore
from opencompany_core.product_workflow import (
    ProductWorkflowError,
    ProductWorkflowRepository,
    STAGES,
)


def _repo(tmp_path):
    store = SQLiteStore(tmp_path / "product-workflow.sqlite3")
    return store, ProductWorkflowRepository(store._connection, store._lock)


def _finish(repo, workflow, stage):
    repo.start_stage(workflow["id"], stage)
    return repo.complete_stage(
        workflow["id"], stage,
        output=f"Completed {stage}",
        artifact_refs=[f"artifact://{stage}/v1"],
        evidence=[f"test evidence for {stage}"],
    )


def test_product_workflow_is_persisted_zero_cost_and_owner_gated(tmp_path):
    store, repo = _repo(tmp_path)
    try:
        workflow = repo.create("Sample icon pack", "Create an original sci-fi game UI icon pack.")
        assert workflow["status"] == "in_progress"
        assert workflow["cost_ceiling_usd"] == 0
        assert workflow["external_actions_enabled"] is False
        assert [stage["key"] for stage in workflow["stages"]] == list(STAGES)
        assert workflow["stages"][0]["status"] == "in_progress"
        assert repo.get(workflow["id"])["title"] == "Sample icon pack"

        for stage in STAGES[:-1]:
            if repo.get(workflow["id"])["stages"][STAGES.index(stage)]["status"] == "pending":
                _finish(repo, workflow, stage)
            else:
                repo.complete_stage(
                    workflow["id"], stage,
                    output=f"Completed {stage}", artifact_refs=[], evidence=["captured"],
                )

        ready = repo.get(workflow["id"])
        assert ready["status"] == "in_progress"
        assert ready["stages"][-1]["status"] == "in_progress"
        try:
            repo.owner_review(workflow["id"], approved=True, rationale="Premature approval")
            assert False, "owner review must wait for CEO review stage completion"
        except ProductWorkflowError:
            pass

        repo.complete_stage(
            workflow["id"], "ceo_review", output="CEO recommends owner review",
            artifact_refs=[], evidence=["internal review recorded"],
        )
        ready = repo.get(workflow["id"])
        assert ready["status"] == "awaiting_owner_review"
        approved = repo.owner_review(workflow["id"], approved=True, rationale="Approved for internal handoff only.")
        assert approved["status"] == "approved_internal"
        assert approved["external_actions_enabled"] is False
    finally:
        store.close()


def test_product_workflow_enforces_sequential_stages_and_records_blockers(tmp_path):
    store, repo = _repo(tmp_path)
    try:
        workflow = repo.create("Test product", "Test brief")
        try:
            repo.start_stage(workflow["id"], "artifact_generation")
            assert False, "out-of-order stage start should fail"
        except ProductWorkflowError:
            pass

        blocked = repo.block_stage(workflow["id"], "opportunity_brief", "No evidence of demand yet.")
        assert blocked["status"] == "blocked"
        assert blocked["stages"][0]["status"] == "blocked"
        assert blocked["stages"][0]["blockers"] == ["No evidence of demand yet."]
    finally:
        store.close()


def test_product_workflow_rejects_missing_evidence_and_unknown_stage(tmp_path):
    store, repo = _repo(tmp_path)
    try:
        workflow = repo.create("Test product", "Test brief")
        try:
            repo.complete_stage(
                workflow["id"], "opportunity_brief",
                output="", artifact_refs=[], evidence=[],
            )
            assert False, "empty output must fail"
        except ProductWorkflowError:
            pass
        try:
            repo.start_stage(workflow["id"], "publish_listing")
            assert False, "unknown stage must fail"
        except ProductWorkflowError:
            pass
    finally:
        store.close()
