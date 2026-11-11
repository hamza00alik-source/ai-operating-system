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
        qa_result=(
            {"passed_checks": ["archive integrity"], "failed_checks": [], "untested_claims": ["visual quality"]}
            if stage == "automated_qa" else None
        ),
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
                    qa_result=(
                        {"passed_checks": ["archive integrity"], "failed_checks": [], "untested_claims": ["visual quality"]}
                        if stage == "automated_qa" else None
                    ),
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


def test_failed_qa_can_return_work_to_production_without_claiming_completion(tmp_path):
    store, repo = _repo(tmp_path)
    try:
        workflow = repo.create("QA rework product", "A product that needs QA rework.")
        for stage in STAGES[:4]:
            current = repo.get(workflow["id"])["stages"][STAGES.index(stage)]
            if current["status"] == "in_progress":
                repo.complete_stage(
                    workflow["id"], stage, output="Done", artifact_refs=[], evidence=["recorded"],
                    qa_result=(
                        {"passed_checks": ["manifest"], "failed_checks": [], "untested_claims": ["visual"]}
                        if stage == "automated_qa" else None
                    ),
                )
            else:
                repo.start_stage(workflow["id"], stage)
                repo.complete_stage(
                    workflow["id"], stage, output="Done", artifact_refs=[], evidence=["recorded"],
                    qa_result=(
                        {"passed_checks": ["manifest"], "failed_checks": [], "untested_claims": ["visual"]}
                        if stage == "automated_qa" else None
                    ),
                )
        repo.start_stage(workflow["id"], "automated_qa")
        blocked = repo.block_stage(workflow["id"], "automated_qa", "Archive integrity failed.")
        assert blocked["status"] == "blocked"
        reworked = repo.return_to_production(workflow["id"], "Rebuild archive with valid manifest.")
        assert reworked["status"] == "in_progress"
        assert reworked["stages"][3]["status"] == "in_progress"
        assert reworked["stages"][4]["status"] == "pending"
        assert reworked["stages"][3]["blockers"]
    finally:
        store.close()


def test_automated_qa_requires_separate_pass_fail_and_untested_lists(tmp_path):
    store, repo = _repo(tmp_path)
    try:
        workflow = repo.create("QA evidence product", "QA report contract.")
        repo.complete_stage(
            workflow["id"], "opportunity_brief", output="Brief done",
            artifact_refs=[], evidence=["brief recorded"],
        )
        repo.start_stage(workflow["id"], "product_specification")
        repo.complete_stage(
            workflow["id"], "product_specification", output="Spec done",
            artifact_refs=[], evidence=["spec recorded"],
        )
        repo.start_stage(workflow["id"], "production_plan")
        repo.complete_stage(
            workflow["id"], "production_plan", output="Plan done",
            artifact_refs=[], evidence=["plan recorded"],
        )
        repo.start_stage(workflow["id"], "artifact_generation")
        repo.complete_stage(
            workflow["id"], "artifact_generation", output="Artifacts generated",
            artifact_refs=["artifact://package/source"], evidence=["file manifest"],
        )
        repo.start_stage(workflow["id"], "automated_qa")
        try:
            repo.complete_stage(
                workflow["id"], "automated_qa", output="QA passed",
                artifact_refs=[], evidence=["some checks"], qa_result=None,
            )
            assert False, "QA must distinguish passed, failed and untested claims"
        except ProductWorkflowError:
            pass
    finally:
        store.close()


def test_product_workflow_api_requires_owner_and_persists_created_job(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from opencompany_app.api import app, get_runtime
    from opencompany_app.runtime import create_runtime

    monkeypatch.setenv("OPENCOMPANY_OWNER_API_KEY", "product-test-owner-key")
    runtime = create_runtime(str(tmp_path / "product-api.sqlite3"))
    app.dependency_overrides[get_runtime] = lambda: runtime
    try:
        with TestClient(app) as client:
            denied = client.post("/product-workflows", json={
                "title": "API test", "brief": "Create an internal product workflow."
            })
            assert denied.status_code == 401

            created = client.post(
                "/product-workflows",
                headers={"X-OpenCompany-API-Key": "product-test-owner-key"},
                json={"title": "API test", "brief": "Create an internal product workflow."},
            )
            assert created.status_code == 200
            payload = created.json()
            assert payload["title"] == "API test"
            assert payload["cost_ceiling_usd"] == 0
            assert payload["external_actions_enabled"] is False

            listed = client.get(
                "/product-workflows",
                headers={"X-OpenCompany-API-Key": "product-test-owner-key"},
            )
            assert listed.status_code == 200
            assert listed.json()["count"] == 1
    finally:
        app.dependency_overrides.clear()
        runtime.close()
