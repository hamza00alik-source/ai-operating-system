from ai_os.db import initialize_database
from ai_os.queue import claim_next_job, enqueue_job, fail_job, finish_job, list_jobs
from ai_os.queue_schemas import JobCreate


def _use_temp_database(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'queue-tests.db'}")
    initialize_database()


def test_filtered_claim_preserves_ineligible_job(monkeypatch, tmp_path):
    _use_temp_database(monkeypatch, tmp_path)
    specialist = enqueue_job(JobCreate(
        job_type="execute_company_step",
        payload={"run_id": "r1", "step_key": "s1"},
    ))
    local = enqueue_job(JobCreate(
        job_type="build_work_packet",
        payload={"agent_id": "researcher", "task": "test"},
    ))

    claimed = claim_next_job("local-worker", allowed_job_types={"build_work_packet"})

    assert claimed["id"] == local["id"]
    jobs = {job["id"]: job for job in list_jobs()}
    assert jobs[specialist["id"]]["status"] == "queued"
    assert jobs[specialist["id"]]["attempts"] == 0
    assert jobs[local["id"]]["status"] == "running"
    assert jobs[local["id"]]["attempts"] == 1


def test_empty_allowlist_does_not_claim_jobs(monkeypatch, tmp_path):
    _use_temp_database(monkeypatch, tmp_path)
    job = enqueue_job(JobCreate(job_type="build_work_packet", payload={"task": "test"}))

    assert claim_next_job("offline-worker", allowed_job_types=set()) is None
    stored = next(item for item in list_jobs() if item["id"] == job["id"])
    assert stored["status"] == "queued"
    assert stored["attempts"] == 0


def test_non_owner_cannot_finish_or_fail_job(monkeypatch, tmp_path):
    _use_temp_database(monkeypatch, tmp_path)
    job = enqueue_job(JobCreate(job_type="build_work_packet", payload={"task": "test"}))
    claim_next_job("worker-a")

    assert finish_job(job["id"], "worker-b", {"ok": True}) is None
    assert fail_job(job["id"], "worker-b", "stale worker") is None
    stored = next(item for item in list_jobs() if item["id"] == job["id"])
    assert stored["status"] == "running"
    assert stored["locked_by"] == "worker-a"


def test_worker_excludes_specialist_jobs_when_model_disabled(monkeypatch):
    from ai_os import worker

    captured = {}
    monkeypatch.setattr("ai_os.worker.get_model_status", lambda: {"enabled": False})
    monkeypatch.setattr(
        "ai_os.worker.claim_next_job",
        lambda worker_id, **kwargs: captured.update(kwargs) or None,
    )

    result = worker.run_once("offline-worker")

    assert captured["allowed_job_types"] == {"build_work_packet", "review_department_plan"}
    assert result["processed"] is False
    assert "remain queued" in result["notice"]
