import pytest

from ai_os import video_jobs


def test_cinecode_and_longcat_workers_only_claim_their_own_jobs(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'providers.db'}")
    monkeypatch.setenv("VIDEO_WORKER_TOKEN", "test-worker-token")

    common = {
        "prompt": "Create an original short film",
        "estimated_cost_minor": 0,
        "approved_budget_minor": 0,
        "currency": "USD",
        "cost_basis": "Owner-managed local worker; no hosted compute",
    }
    cine = video_jobs.create_job(
        **common, provider="cinecode", idempotency_key="cinecode-job-1"
    )
    longcat = video_jobs.create_job(
        **common, provider="longcat-video", idempotency_key="longcat-job-1"
    )
    video_jobs.decide_job(cine["id"], "approved")
    video_jobs.decide_job(longcat["id"], "approved")

    cine_claim = video_jobs.claim_job("cinecode-worker-1", provider="cinecode")
    assert cine_claim["id"] == cine["id"]
    assert cine_claim["provider"] == "cinecode"

    longcat_claim = video_jobs.claim_job("longcat-worker-1", provider="longcat-video")
    assert longcat_claim["id"] == longcat["id"]
    assert longcat_claim["provider"] == "longcat-video"

    assert video_jobs.worker_status("cinecode")["worker_connected"] is True
    assert video_jobs.worker_status("longcat-video")["worker_connected"] is True


def test_unknown_video_provider_cannot_claim_jobs(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'invalid-provider.db'}")
    with pytest.raises(ValueError, match="Unsupported video provider"):
        video_jobs.claim_job("unknown-worker", provider="unknown")
