from opencompany_core.persistence import SQLiteStore
from opencompany_core.product_artifacts import generate_product_blueprint, verify_product_blueprint
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


def test_product_workflow_rejects_completion_without_evidence(tmp_path):
    store, repo = _repo(tmp_path)
    try:
        workflow = repo.create("Evidence required", "Every completed stage needs evidence.")
        try:
            repo.complete_stage(
                workflow["id"], "opportunity_brief",
                output="The stage claims to be complete.", artifact_refs=[], evidence=[],
            )
            assert False, "stage completion without evidence must fail"
        except ProductWorkflowError:
            pass
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


def test_blueprint_generator_creates_safe_zip_with_truthful_scope_and_manifest(tmp_path):
    import json
    import zipfile
    from uuid import uuid4

    workflow_id = uuid4()
    artifact = generate_product_blueprint(
        workflow_id=workflow_id,
        title="Original UI Toolkit",
        brief="Create a collection of original UI icons for a desktop game.",
        artifact_root=tmp_path / "artifacts",
    )
    path = tmp_path / "artifacts" / f"{workflow_id}.zip"
    assert artifact["status"] == "blueprint_only_not_a_finished_product"
    assert artifact["size_bytes"] > 0
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        names = set(archive.namelist())
        assert names == {
            "README.md", "PRODUCT_SPEC.md", "PRODUCTION_PLAN.md",
            "QA_CHECKLIST.md", "LISTING_DRAFT.md", "SOURCE_BRIEF.md", "manifest.json",
        }
        readme = archive.read("README.md").decode()
        assert "not a finished commercial product" in readme
        qa = archive.read("QA_CHECKLIST.md").decode()
        assert "not executed" in qa
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["provider_cost_usd"] == 0
        assert manifest["external_actions_performed"] is False
        assert manifest["status"] == "blueprint_only_not_a_finished_product"


def test_product_workflow_api_generates_and_serves_owner_authenticated_blueprint(tmp_path, monkeypatch):
    import io
    import zipfile
    from fastapi.testclient import TestClient
    from opencompany_app.api import app, get_runtime
    from opencompany_app.runtime import create_runtime

    monkeypatch.setenv("OPENCOMPANY_OWNER_API_KEY", "product-artifact-test-key")
    runtime = create_runtime(str(tmp_path / "product-artifact-api.sqlite3"))
    app.dependency_overrides[get_runtime] = lambda: runtime
    headers = {"X-OpenCompany-API-Key": "product-artifact-test-key"}
    try:
        with TestClient(app) as client:
            created = client.post(
                "/product-workflows", headers=headers,
                json={"title": "Starter Pack", "brief": "Create an original starter pack."},
            )
            assert created.status_code == 200
            workflow = created.json()
            workflow_id = workflow["id"]
            repo = ProductWorkflowRepository(runtime.store._connection, runtime.store._lock)
            for stage in STAGES[:3]:
                current = repo.get(workflow_id)["stages"][STAGES.index(stage)]
                if current["status"] == "in_progress":
                    repo.complete_stage(
                        workflow_id, stage, output=f"{stage} done",
                        artifact_refs=[], evidence=["recorded"],
                    )
                else:
                    repo.start_stage(workflow_id, stage)
                    repo.complete_stage(
                        workflow_id, stage, output=f"{stage} done",
                        artifact_refs=[], evidence=["recorded"],
                    )

            repo.start_stage(workflow_id, "artifact_generation")
            generated = client.post(f"/product-workflows/{workflow_id}/generate-blueprint", headers=headers)
            assert generated.status_code == 200, generated.text
            payload = generated.json()
            assert payload["artifact"]["status"] == "blueprint_only_not_a_finished_product"
            assert payload["next_stage"] == "automated_qa"
            assert "not a finished" in payload["notice"]
            current = repo.get(workflow_id)
            assert current["stages"][3]["status"] == "completed"
            assert current["stages"][4]["status"] == "pending"
            repo.start_stage(workflow_id, "automated_qa")
            qa_response = client.post(f"/product-workflows/{workflow_id}/run-automated-qa", headers=headers)
            assert qa_response.status_code == 200, qa_response.text
            qa_payload = qa_response.json()
            assert qa_payload["workflow_status"] == "in_progress"
            assert qa_payload["qa_result"]["failed_checks"] == []
            assert "visual quality of any future product assets" in qa_payload["qa_result"]["untested_claims"]
            assert repo.get(workflow_id)["stages"][4]["status"] == "completed"

            downloaded = client.get(payload["download_path"], headers=headers)
            assert downloaded.status_code == 200
            assert downloaded.headers["content-type"].startswith("application/zip")
            with zipfile.ZipFile(io.BytesIO(downloaded.content)) as archive:
                assert archive.testzip() is None
    finally:
        app.dependency_overrides.clear()
        runtime.close()


def test_failed_automated_qa_blocks_workflow_and_preserves_failure_evidence(tmp_path):
    store, repo = _repo(tmp_path)
    try:
        workflow = repo.create("QA fail product", "Product used to test failed QA.")
        for stage in STAGES[:4]:
            current = repo.get(workflow["id"])["stages"][STAGES.index(stage)]
            if current["status"] == "in_progress":
                repo.complete_stage(
                    workflow["id"], stage, output="Done", artifact_refs=["artifact://sample"],
                    evidence=["recorded"],
                )
            else:
                repo.start_stage(workflow["id"], stage)
                repo.complete_stage(
                    workflow["id"], stage, output="Done", artifact_refs=["artifact://sample"],
                    evidence=["recorded"],
                )
        repo.start_stage(workflow["id"], "automated_qa")
        failed = repo.complete_stage(
            workflow["id"], "automated_qa", output="QA failed",
            artifact_refs=["artifact://sample"], evidence=["failed:checksum"],
            qa_result={
                "passed_checks": ["ZIP CRC integrity"],
                "failed_checks": ["manifest checksum mismatch for PRODUCT_SPEC.md"],
                "untested_claims": ["visual quality"],
            },
        )
        assert failed["status"] == "blocked"
        assert failed["stages"][4]["status"] == "blocked"
        assert failed["stages"][4]["qa_result"]["failed_checks"]
        rework = repo.return_to_production(workflow["id"], "Fix manifest mismatch.")
        assert rework["stages"][3]["status"] == "in_progress"
        assert rework["stages"][4]["status"] == "pending"
    finally:
        store.close()


def test_blueprint_verifier_reports_passed_and_untested_separately(tmp_path):
    from uuid import uuid4
    workflow_id = uuid4()
    artifact = generate_product_blueprint(
        workflow_id=workflow_id,
        title="Verified blueprint",
        brief="Create a starter pack.",
        artifact_root=tmp_path / "artifacts",
    )
    report = verify_product_blueprint(tmp_path / "artifacts" / f"{workflow_id}.zip")
    assert report["failed_checks"] == []
    assert "ZIP CRC integrity" in report["passed_checks"]
    assert report["untested_claims"]
    assert artifact["status"] == "blueprint_only_not_a_finished_product"


def test_product_ai_stage_runs_only_with_active_role_and_zero_cost_gateway(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from uuid import uuid4
    from opencompany_app.api import app, get_runtime
    from opencompany_app.runtime import create_runtime
    from opencompany_core.domain import AgentProfile, AgentState
    from opencompany_core.execution import AgentDeliverable
    from opencompany_core.model_gateway import ModelResult
    from opencompany_core.organization import default_organization
    from opencompany_core.workforce import default_workforce

    class FakeGateway:
        def complete(self, request, *, request_budget_usd, preferred_provider=None):
            assert request_budget_usd == 0.0
            assert preferred_provider == "unorouter"
            return ModelResult("Evidence-led opportunity brief.", "unorouter", "test:free", 0.0, 10, 20)

    monkeypatch.setenv("OPENCOMPANY_OWNER_API_KEY", "product-ai-stage-test-key")
    runtime = create_runtime(str(tmp_path / "product-ai-stage.sqlite3"))
    runtime.gateway = FakeGateway()
    department = default_organization().get("product-innovation")
    role = default_workforce().get("product_planning_lead")
    runtime.store.save_agent(AgentProfile(
        id=uuid4(), name="Product Planning Lead", department=department.key,
        purpose="Prepare product discovery briefs.", capabilities=role.capabilities,
        state=AgentState.ACTIVE, role_key=role.key, team_key="management",
    ))
    app.dependency_overrides[get_runtime] = lambda: runtime
    try:
        with TestClient(app) as client:
            headers = {"X-OpenCompany-API-Key": "product-ai-stage-test-key"}
            created = client.post("/product-workflows", headers=headers, json={
                "title": "Test product", "brief": "Assess an original downloadable product."
            })
            assert created.status_code == 200, created.text
            workflow_id = created.json()["id"]
            result = client.post(f"/product-workflows/{workflow_id}/run-ai-stage", headers=headers)
            assert result.status_code == 200, result.text
            assert result.json()["stage"] == "opportunity_brief"
            assert result.json()["reported_cost_usd"] == 0.0
            saved = client.get(f"/product-workflows/{workflow_id}", headers=headers).json()
            assert saved["stages"][0]["status"] == "completed"
            assert saved["stages"][0]["output"] == "Evidence-led opportunity brief."
            assert "reported_cost_usd:0" in saved["stages"][0]["evidence"]
    finally:
        app.dependency_overrides.clear()
        runtime.close()
