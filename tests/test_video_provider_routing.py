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



def test_provider_worker_cannot_recover_another_providers_expired_lease(monkeypatch, tmp_path):
    from datetime import datetime, timedelta, timezone

    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'lease-isolation.db'}")
    monkeypatch.setenv("VIDEO_WORKER_TOKEN", "longcat-secret")
    base = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(video_jobs, "_now", lambda: base)

    common = {
        "prompt": "Provider isolation lease test",
        "estimated_cost_minor": 0,
        "approved_budget_minor": 0,
        "currency": "USD",
        "cost_basis": "Local protocol test; no external compute",
    }
    longcat = video_jobs.create_job(
        **common, provider="longcat-video", idempotency_key="longcat-expiry-1"
    )
    cinecode = video_jobs.create_job(
        **common, provider="cinecode", idempotency_key="cinecode-expiry-1"
    )
    video_jobs.decide_job(longcat["id"], "approved")
    video_jobs.decide_job(cinecode["id"], "approved")

    first_longcat_claim = video_jobs.claim_job(
        "longcat-worker", lease_seconds=30, provider="longcat-video"
    )
    assert first_longcat_claim["id"] == longcat["id"]

    monkeypatch.setattr(video_jobs, "_now", lambda: base + timedelta(seconds=31))
    cine_claim = video_jobs.claim_job(
        "cinecode-worker", lease_seconds=30, provider="cinecode"
    )
    assert cine_claim["id"] == cinecode["id"]
    assert video_jobs.get_job(longcat["id"])["status"] == "running"

    reclaimed_longcat = video_jobs.claim_job(
        "longcat-worker", lease_seconds=30, provider="longcat-video"
    )
    assert reclaimed_longcat["id"] == longcat["id"]
    assert reclaimed_longcat["attempts"] == 2



def test_worker_capabilities_are_sanitized_and_visible(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'capabilities.db'}")
    video_jobs.claim_job(
        "cinecode-worker",
        provider="cinecode",
        capabilities={
            "agent": "codex",
            "source_commit": "c8a3e7552699360a2b0142c9620882af2069eedb",
            "disk_free_bytes": 123456,
            "api_key": "must-not-be-stored",
            "arbitrary": "untrusted",
        },
    )
    status = video_jobs.worker_status("cinecode")
    assert status["worker_connected"] is True
    assert status["worker_capabilities"] == {
        "agent": "codex",
        "source_commit": "c8a3e7552699360a2b0142c9620882af2069eedb",
        "disk_free_bytes": 123456,
    }
    assert "api_key" not in str(status)



def test_worker_identity_cannot_be_reused_across_video_providers(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'provider-worker-id.db'}")
    video_jobs.claim_job("shared-worker-id", provider="cinecode")
    with pytest.raises(ValueError, match="different video provider"):
        video_jobs.claim_job("shared-worker-id", provider="longcat-video")
