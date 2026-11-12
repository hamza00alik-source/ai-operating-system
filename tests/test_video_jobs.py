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
