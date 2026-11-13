from opencompany_core.persistence import SQLiteStore
from opencompany_core.product_rd import ProductRDError, ProductRDRepository, PRODUCT_STAGES


def _repo(tmp_path):
    store = SQLiteStore(tmp_path / "product-rd.sqlite3")
    return store, ProductRDRepository(store._connection, store._lock)


def _complete(repo, workflow_id, stage):
    qa = (
        {"passed_checks": ["manifest checksum"], "failed_checks": [],
         "untested_claims": ["visual quality", "engine compatibility"]}
        if stage == "automated_qa" else None
    )
    return repo.complete_stage(
        workflow_id, stage, output=f"Recorded {stage}",
        evidence=[f"Evidence captured for {stage}"],
        artifact_refs=[f"test-artifact:{stage}"], qa_result=qa,
    )


def test_product_rd_workflow_is_business_scoped_zero_cost_and_audited(tmp_path):
    store, repo = _repo(tmp_path)
    try:
        workflow = repo.create(
            title="Original sci-fi UI icon pack",
            brief="Create a downloadable original game UI icon pack.",
            business_id="digital-products",
        )
        assert workflow["business_id"] == "digital-products"
        assert workflow["cost_ceiling_usd"] == 0
        assert workflow["external_actions_enabled"] is False
        assert [stage["key"] for stage in workflow["stages"]] == list(PRODUCT_STAGES)
        assert workflow["stages"][0]["owner_role"] == "market_intelligence_analyst"
        assert workflow["stages"][1]["owner_role"] == "product_planning_lead"
        assert workflow["stages"][7]["owner_role"] == "marketplace_operations_analyst"
        assert workflow["stages"][8]["owner_role"] == "chief_executive_orchestrator"

        for stage in PRODUCT_STAGES:
            workflow = _complete(repo, workflow["id"], stage)

        assert workflow["status"] == "awaiting_owner_review"
        approved = repo.owner_review(
            workflow["id"], approved=True, rationale="Accepted for internal review only."
        )
        assert approved["status"] == "approved_internal"
        assert approved["external_actions_enabled"] is False
        assert store.verify_audit_chain()
    finally:
        store.close()


def test_product_rd_rejects_core_and_cross_business_scope(tmp_path):
    store, repo = _repo(tmp_path)
    try:
        try:
            repo.create(title="Bad scope", brief="Core is not a commercial business.", business_id="core")
            assert False, "core must not own a commercial product workflow"
        except ProductRDError:
            pass

        repo.create(title="Agency item", brief="Agency product work.", business_id="physical-agency")
        repo.create(title="Digital item", brief="Digital product work.", business_id="digital-products")
        assert len(repo.list(business_id="physical-agency")) == 1
        assert len(repo.list(business_id="digital-products")) == 1
    finally:
        store.close()


def test_product_rd_qa_failure_blocks_and_rework_resets_downstream_stages(tmp_path):
    store, repo = _repo(tmp_path)
    try:
        workflow = repo.create(title="QA pilot", brief="A product used to verify the rework loop.")
        for stage in PRODUCT_STAGES[:4]:
            workflow = _complete(repo, workflow["id"], stage)

        failed = repo.complete_stage(
            workflow["id"], "automated_qa", output="QA found a missing required file.",
            evidence=["Required-file check failed"],
            artifact_refs=["test-artifact:qa-failure"],
            qa_result={"passed_checks": [], "failed_checks": ["missing README"],
                       "untested_claims": ["visual quality"]},
        )
        assert failed["status"] == "blocked"
        assert failed["stages"][4]["status"] == "blocked"

        repaired = repo.return_to_production(
            workflow["id"], rationale="Regenerate the package with the missing README."
        )
        assert repaired["status"] == "in_progress"
        assert repaired["stages"][3]["status"] == "in_progress"
        assert repaired["stages"][4]["status"] == "pending"
        assert repaired["stages"][5]["status"] == "pending"
    finally:
        store.close()


def test_product_rd_cannot_complete_stage_without_artifact_reference(tmp_path):
    store, repo = _repo(tmp_path)
    try:
        workflow = repo.create(title="Missing artifact", brief="Artifact references are mandatory.")
        try:
            repo.complete_stage(
                workflow["id"], "opportunity_brief",
                output="A stage without an artifact must not complete.",
                evidence=["No artifact was attached."],
            )
            assert False, "missing artifact references must block completion"
        except ProductRDError:
            pass
    finally:
        store.close()


def test_product_rd_cannot_skip_stages_or_approve_incomplete_work(tmp_path):
    store, repo = _repo(tmp_path)
    try:
        workflow = repo.create(title="Sequence check", brief="Stages must be sequential.")
        try:
            repo.complete_stage(
                workflow["id"], "product_specification", output="Skipped the brief.",
                evidence=["No valid preceding stage."],
            )
            assert False, "a pending stage must not be completed"
        except ProductRDError:
            pass
        try:
            repo.owner_review(workflow["id"], approved=True, rationale="Premature approval.")
            assert False, "owner approval must wait for all stages"
        except ProductRDError:
            pass
        try:
            repo.complete_stage(
                workflow["id"], "opportunity_brief", output="Paid work is not allowed.",
                evidence=["Zero-dollar policy test"], cost_actual_usd=0.01,
            )
            assert False, "non-zero costs must be blocked"
        except ProductRDError:
            pass
    finally:
        store.close()



def test_product_rd_attaches_one_work_item_only_to_active_stage(tmp_path):
    store, repo = _repo(tmp_path)
    try:
        workflow = repo.create(title="Delegation check", brief="Test stage work-item linkage.")
        stage_id = "00000000-0000-4000-8000-000000000001"
        updated = repo.attach_work_item(workflow["id"], "opportunity_brief", stage_id)
        assert updated["stages"][0]["work_item_id"] == stage_id
        try:
            repo.attach_work_item(workflow["id"], "opportunity_brief", "00000000-0000-4000-8000-000000000002")
            assert False, "an active stage must not accept a second work item"
        except ProductRDError:
            pass
        try:
            repo.attach_work_item(workflow["id"], "product_specification", stage_id)
            assert False, "a pending stage must not accept a work item"
        except ProductRDError:
            pass
    finally:
        store.close()
