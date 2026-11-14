from fastapi.testclient import TestClient

from ai_os.api import app


def test_video_job_requires_explicit_cost_and_owner_approval(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_API_KEY", "test-owner-key")
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'video.db'}")
    headers = {"X-API-Key": "test-owner-key"}

    with TestClient(app) as client:
        payload = {
            "prompt": "Original anime archer hero cinematic reveal",
            "provider": "longcat-video",
            "idempotency_key": "video-job-001",
            "parameters": {"resolution": "720p"},
            "estimated_cost_minor": 0,
            "approved_budget_minor": 0,
            "currency": "USD",
            "cost_basis": "Owner-managed local GPU; no hosted compute authorized",
        }
        created = client.post("/video/jobs", headers=headers, json=payload)
        assert created.status_code == 201
        job = created.json()
        assert job["status"] == "awaiting_approval"

        repeated = client.post("/video/jobs", headers=headers, json=payload)
        assert repeated.status_code == 201
        assert repeated.json()["id"] == job["id"]

        approved = client.post(
            f"/video/jobs/{job['id']}/decision",
            headers=headers,
            json={"decision": "approved", "approval_note": "Local-only test approval"},
        )
        assert approved.status_code == 200
        assert approved.json()["job"]["status"] == "queued"
        assert approved.json()["generation_started"] is False


def test_video_job_cannot_exceed_approved_budget(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_API_KEY", "test-owner-key")
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'video-budget.db'}")
    headers = {"X-API-Key": "test-owner-key"}
    with TestClient(app) as client:
        created = client.post("/video/jobs", headers=headers, json={
            "prompt": "Test", "idempotency_key": "budget-001",
            "estimated_cost_minor": 101, "approved_budget_minor": 100,
            "currency": "USD", "cost_basis": "Quoted estimate",
        })
        assert created.status_code == 201
        job_id = created.json()["id"]
        response = client.post(
            f"/video/jobs/{job_id}/decision", headers=headers,
            json={"decision": "approved"},
        )
        assert response.status_code == 409
        assert client.get(f"/video/jobs/{job_id}", headers=headers).json()["status"] == "awaiting_approval"

def test_creator_clipping_job_is_claimed_only_by_matching_worker(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_API_KEY", "test-owner-key")
    monkeypatch.setenv("VIDEO_WORKER_TOKEN", "test-worker-token")
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'creator-clipping.db'}")
    owner_headers = {"X-API-Key": "test-owner-key"}
    worker_headers = {"X-Video-Worker-Token": "test-worker-token"}

    with TestClient(app) as client:
        created = client.post("/video/jobs", headers=owner_headers, json={
            "prompt": "Create the strongest short clip from authorized source footage",
            "provider": "creator-clipping",
            "idempotency_key": "creator-clip-001",
            "parameters": {"source_path": "source.mp4", "clip_seconds": 30},
            "estimated_cost_minor": 0,
            "approved_budget_minor": 0,
            "currency": "USD",
            "cost_basis": "Owner-provided local footage and local CPU worker",
        })
        assert created.status_code == 201
        job = created.json()
        assert job["status"] == "awaiting_approval"

        approved = client.post(
            f"/video/jobs/{job['id']}/decision", headers=owner_headers,
            json={"decision": "approved", "approval_note": "Local clipping test"},
        )
        assert approved.status_code == 200
        assert approved.json()["job"]["status"] == "queued"

        wrong_worker = client.post("/video/worker/claim", headers=worker_headers, json={
            "worker_id": "longcat-test", "lease_seconds": 60, "provider": "longcat-video",
        })
        assert wrong_worker.status_code == 200
        assert wrong_worker.json() is None

        clip_worker = client.post("/video/worker/claim", headers=worker_headers, json={
            "worker_id": "clipper-test", "lease_seconds": 60, "provider": "creator-clipping",
        })
        assert clip_worker.status_code == 200
        assert clip_worker.json()["id"] == job["id"]
        assert clip_worker.json()["provider"] == "creator-clipping"
