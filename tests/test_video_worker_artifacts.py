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
    worker_headers = {"X-Video-Worker-Token": "test-video-worker-token", "X-Video-Provider": "longcat-video"}

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
    worker_headers = {"X-Video-Worker-Token": "test-video-worker-token", "X-Video-Provider": "longcat-video"}

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



def test_cinecode_worker_can_upload_private_mp4_with_its_own_credential(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_API_KEY", "test-owner-key")
    monkeypatch.setenv("VIDEO_CINECODE_WORKER_TOKEN", "test-cinecode-worker-token")
    monkeypatch.setenv("VIDEO_WORKER_TOKEN", "different-longcat-token")
    monkeypatch.setenv("PUBLIC_API_BASE_URL", "https://api.example.test")
    monkeypatch.setenv("VIDEO_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'cinecode-artifact.db'}")

    owner_headers = {"X-API-Key": "test-owner-key"}
    cinecode_headers = {
        "X-Video-Worker-Token": "test-cinecode-worker-token",
        "X-Video-Provider": "cinecode",
    }
    with TestClient(app) as client:
        created = client.post("/video/jobs", headers=owner_headers, json={
            "prompt": "Cinecode private artifact integration test",
            "provider": "cinecode",
            "idempotency_key": "cinecode-artifact-001",
            "parameters": {},
            "estimated_cost_minor": 0,
            "approved_budget_minor": 0,
            "currency": "USD",
            "cost_basis": "Local protocol test; no paid compute",
        })
        assert created.status_code == 201
        job_id = created.json()["id"]
        approved = client.post(
            f"/video/jobs/{job_id}/decision",
            headers=owner_headers,
            json={"decision": "approved", "approval_note": "Cinecode API integration test"},
        )
        assert approved.status_code == 200

        wrong_provider_secret = client.post(
            "/video/worker/claim",
            headers={
                "X-Video-Worker-Token": "different-longcat-token",
                "X-Video-Provider": "cinecode",
            },
            json={"worker_id": "wrong-cinecode-worker", "provider": "cinecode"},
        )
        assert wrong_provider_secret.status_code == 401

        claim = client.post(
            "/video/worker/claim",
            headers=cinecode_headers,
            json={"worker_id": "cinecode-test-worker", "provider": "cinecode"},
        )
        assert claim.status_code == 200
        assert claim.json()["id"] == job_id
        lease = claim.json()["lease_token"]

        report_text = b"# Cinecode production report\\n\\nMode: Quick\\nLicence: original generated assets\\n"
        report_upload = client.put(
            f"/video/worker/jobs/{job_id}/report",
            content=report_text,
            headers={
                **cinecode_headers,
                "X-Job-Lease": lease,
                "Content-Type": "text/markdown; charset=utf-8",
            },
        )
        assert report_upload.status_code == 200

        mp4 = b"\x00\x00\x00\x18ftypisom" + b"cinecode-test-payload"
        uploaded = client.put(
            f"/video/worker/jobs/{job_id}/artifact",
            content=mp4,
            headers={
                **cinecode_headers,
                "X-Job-Lease": lease,
                "Content-Type": "video/mp4",
            },
        )
        assert uploaded.status_code == 200
        assert uploaded.json()["provider"] == "cinecode"
        assert uploaded.json()["status"] == "succeeded"
        downloaded = client.get(f"/video/artifacts/{job_id}", headers=owner_headers)
        assert downloaded.status_code == 200
        assert downloaded.content == mp4
        report_download = client.get(f"/video/reports/{job_id}", headers=owner_headers)
        assert report_download.status_code == 200
        assert "Licence: original generated assets" in report_download.text
