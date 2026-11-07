from ai_os.db import initialize_database
from ai_os.queue import (
    claim_next_job,
    enqueue_job,
    fail_job,
    finish_job,
    list_jobs,
)
from ai_os.queue_schemas import JobCreate


def _use_temp_database(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'queue-tests.db'}")
    initialize_database()


def test_filtered_claim_leaves_model_job_queued_and_claims_allowed_local_job(
    monkeypatch, tmp_path
):
    _use_temp_database(monkeypatch, tmp_path)
    model_job = enqueue_job(
        JobCreate(job_type="execute_company_step", payload={"run_id": "r1", "step_key": "s1"})
    )
    local_job = enqueue_job(
        JobCreate(job_type="build_work_packet", payload={"agent_id": "researcher", "task": "test"})
    )

    claimed = claim_next_job(
        "local-worker",
        allowed_job_types={"build_work_packet", "review_department_plan"},
    )

    assert claimed is not None
    assert claimed["id"] == local_job["id"]
    jobs = {job["id"]: job for job in list_jobs()}
    assert jobs[model_job["id"]]["status"] == "queued"
    assert jobs[model_job["id"]]["attempts"] == 0
    assert jobs[local_job["id"]]["status"] == "running"
    assert jobs[local_job["id"]]["attempts"] == 1


def test_empty_allowlist_does_not_claim_or_increment_any_job(monkeypatch, tmp_path):
    _use_temp_database(monkeypatch, tmp_path)
    job = enqueue_job(
        JobCreate(job_type="execute_company_step", payload={"run_id": "r1", "step_key": "s1"})
    )

    assert claim_next_job("offline-worker", allowed_job_types=set()) is None
    stored = next(item for item in list_jobs() if item["id"] == job["id"])
    assert stored["status"] == "queued"
    assert stored["attempts"] == 0


def test_only_current_worker_can_finish_a_claimed_job(monkeypatch, tmp_path):
    _use_temp_database(monkeypatch, tmp_path)
    job = enqueue_job(
        JobCreate(job_type="build_work_packet", payload={"agent_id": "researcher", "task": "test"})
    )
    claimed = claim_next_job("worker-a")
    assert claimed["id"] == job["id"]

    assert finish_job(job["id"], "worker-b", {"ok": True}) is None
    stored = next(item for item in list_jobs() if item["id"] == job["id"])
    assert stored["status"] == "running"
    assert stored["locked_by"] == "worker-a"


def test_only_current_worker_can_fail_a_claimed_job(monkeypatch, tmp_path):
    _use_temp_database(monkeypatch, tmp_path)
    job = enqueue_job(
        JobCreate(job_type="build_work_packet", payload={"agent_id": "researcher", "task": "test"})
    )
    claimed = claim_next_job("worker-a")
    assert claimed["id"] == job["id"]

    assert fail_job(job["id"], "worker-b", "stale worker") is None
    stored = next(item for item in list_jobs() if item["id"] == job["id"])
    assert stored["status"] == "running"
    assert stored["locked_by"] == "worker-a"
