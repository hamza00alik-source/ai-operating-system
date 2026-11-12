from fastapi.testclient import TestClient

from ai_os.api import app


def test_authenticated_worker_can_upload_private_mp4_artifact(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_API_KEY", "test-owner-key")
    monkeypatch.setenv("VIDEO_WORKER_TOKEN", "test-video-worker-token")
    monkeypatch.setenv("PUBLIC_API_BASE_URL", "https://api.example.test")
    monkeypatch.setenv("VIDEO_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'worker-artifact.db'}")

    owner_headers = {"X-API-Key": "test-owner-key"}
    worker_headers = {"X-Video-Worker-Token": "test-video-worker-token"}

    with TestClient(app) as client:
        created = client.post("/video/jobs", headers=owner_headers, json={
            "prompt": "A short synthetic video used only for protocol testing",
            "provider": "longcat-video",
            "idempotency_key": "worker-artifact-001",
            "parameters": {},
            "estimated_cost_minor": 0,
            "approved_budget_minor": 0,
            "currency": "USD",
            "cost_basis": "Protocol test; no GPU compute is invoked",
        })
        assert created.status_code == 201
        job_id = created.json()["id"]

        approved = client.post(
            f"/video/jobs/{job_id}/decision",
            headers=owner_headers,
            json={"decision": "approved", "approval_note": "Protocol test only"},
        )
        assert approved.status_code == 200
        assert approved.json()["job"]["status"] == "queued"

        claim = client.post(
            "/video/worker/claim",
            headers=worker_headers,
            json={"worker_id": "pytest-worker", "lease_seconds": 120},
        )
        assert claim.status_code == 200
        lease = claim.json()["lease_token"]
        assert claim.json()["id"] == job_id

        mp4 = b"\x00\x00\x00\x18ftypisom" + b"synthetic-mp4-payload"
        unauthorized = client.put(
            f"/video/worker/jobs/{job_id}/artifact",
            content=mp4,
            headers={"Content-Type": "video/mp4", "X-Job-Lease": lease},
        )
        assert unauthorized.status_code == 401

        uploaded = client.put(
            f"/video/worker/jobs/{job_id}/artifact",
            content=mp4,
            headers={
                **worker_headers,
                "X-Job-Lease": lease,
                "Content-Type": "video/mp4",
            },
        )
        assert uploaded.status_code == 200
        assert uploaded.json()["status"] == "succeeded"
        assert uploaded.json()["result_uri"] == f"https://api.example.test/video/artifacts/{job_id}"

        artifact = client.get(f"/video/artifacts/{job_id}", headers=owner_headers)
        assert artifact.status_code == 200
        assert artifact.content == mp4
        assert (tmp_path / "artifacts" / f"{job_id}.mp4").read_bytes() == mp4


def test_worker_cannot_upload_after_owner_cancellation(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_API_KEY", "test-owner-key")
    monkeypatch.setenv("VIDEO_WORKER_TOKEN", "test-video-worker-token")
    monkeypatch.setenv("PUBLIC_API_BASE_URL", "https://api.example.test")
    monkeypatch.setenv("VIDEO_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'worker-cancel.db'}")

    owner_headers = {"X-API-Key": "test-owner-key"}
    worker_headers = {"X-Video-Worker-Token": "test-video-worker-token"}

    with TestClient(app) as client:
        created = client.post("/video/jobs", headers=owner_headers, json={
            "prompt": "Cancellation protocol test",
            "provider": "longcat-video",
            "idempotency_key": "worker-cancel-001",
            "parameters": {},
            "estimated_cost_minor": 0,
            "approved_budget_minor": 0,
            "currency": "USD",
            "cost_basis": "Protocol test; no GPU compute is invoked",
        })
        assert created.status_code == 201
        job_id = created.json()["id"]
        assert client.post(
            f"/video/jobs/{job_id}/decision",
            headers=owner_headers,
            json={"decision": "approved"},
        ).status_code == 200

        claim = client.post(
            "/video/worker/claim",
            headers=worker_headers,
            json={"worker_id": "pytest-worker", "lease_seconds": 120},
        )
        assert claim.status_code == 200
        lease = claim.json()["lease_token"]

        cancelled = client.post(f"/video/jobs/{job_id}/cancel", headers=owner_headers)
        assert cancelled.status_code == 200
        assert cancelled.json()["job"]["cancel_requested"] is True

        response = client.put(
            f"/video/worker/jobs/{job_id}/artifact",
            content=b"\x00\x00\x00\x18ftypisomsynthetic",
            headers={
                **worker_headers,
                "X-Job-Lease": lease,
                "Content-Type": "video/mp4",
            },
        )
        assert response.status_code == 409
        assert client.get(f"/video/jobs/{job_id}", headers=owner_headers).json()["status"] == "running"
        assert not (tmp_path / "artifacts" / f"{job_id}.mp4").exists()
