from opencompany_core import product_rd_coordinator as coordinator_module
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
        assert store.list_work_items(business_id="digital-products", limit=10) == []
    finally:
        store.close()
