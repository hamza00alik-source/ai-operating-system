import pytest

from ai_os import video_jobs


def _approved(tmp_path, monkeypatch, key="worker-test"):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'worker.db'}")
    job = video_jobs.create_job(
        prompt="A cinematic anime archer reveal",
        idempotency_key=key,
        estimated_cost_minor=0,
        approved_budget_minor=0,
        currency="USD",
        cost_basis="Owner-managed GPU; no hosted compute",
        max_attempts=2,
    )
    return video_jobs.decide_job(job["id"], "approved")


def test_claim_requires_approval_and_lease_token(tmp_path, monkeypatch):
    job = _approved(tmp_path, monkeypatch)
    assert job["status"] == "queued"
    claimed = video_jobs.claim_job("gpu-worker-a", 60)
    assert claimed["status"] == "running"
    assert claimed["attempts"] == 1
    assert claimed["lease_token"]
    with pytest.raises(PermissionError):
        video_jobs.heartbeat(job["id"], "wrong-token", progress=5)
    beat = video_jobs.heartbeat(job["id"], claimed["lease_token"], progress=20, message="loading")
    assert beat["cancel_requested"] is False
    assert video_jobs.get_job(job["id"])["progress"] == 20


def test_retry_and_bounded_attempts(tmp_path, monkeypatch):
    job = _approved(tmp_path, monkeypatch, "retry-test")
    first = video_jobs.claim_job("gpu-worker-a", 60)
    retried = video_jobs.fail_job(job["id"], first["lease_token"], error="temporary CUDA OOM", retryable=True)
    assert retried["status"] == "queued"
    second = video_jobs.claim_job("gpu-worker-b", 60)
    assert second["attempts"] == 2
    failed = video_jobs.fail_job(job["id"], second["lease_token"], error="still failing", retryable=True)
    assert failed["status"] == "failed"
    assert failed["attempts"] == 2


def test_owner_cancellation_is_visible_to_running_worker(tmp_path, monkeypatch):
    job = _approved(tmp_path, monkeypatch, "cancel-test")
    claimed = video_jobs.claim_job("gpu-worker-a", 60)
    cancelled = video_jobs.cancel_job(job["id"])
    assert cancelled["status"] == "running"
    assert cancelled["cancel_requested"] is True
    beat = video_jobs.heartbeat(job["id"], claimed["lease_token"], progress=50)
    assert beat["cancel_requested"] is True
    final = video_jobs.fail_job(job["id"], claimed["lease_token"], error="Cancelled by owner", retryable=False)
    assert final["status"] == "cancelled"


def test_worker_can_report_success_and_events_are_audited(tmp_path, monkeypatch):
    job = _approved(tmp_path, monkeypatch, "complete-test")
    claimed = video_jobs.claim_job("gpu-worker-a", 60)
    done = video_jobs.complete_job(
        job["id"], claimed["lease_token"],
        result_uri="https://opencompany.example/video/artifacts/" + job["id"],
        metadata={"content_type": "video/mp4", "size_bytes": 1234},
    )
    assert done["status"] == "succeeded"
    assert done["progress"] == 100
    events = video_jobs.list_events(job["id"])
    assert [event["event"] for event in events][-1] == "succeeded"


def test_unapproved_jobs_are_never_claimed(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'unapproved.db'}")
    video_jobs.create_job(
        prompt="Pending owner review",
        idempotency_key="unapproved",
        estimated_cost_minor=0,
        approved_budget_minor=0,
        currency="USD",
        cost_basis="No cost",
    )
    assert video_jobs.claim_job("gpu-worker-a", 60) is None
