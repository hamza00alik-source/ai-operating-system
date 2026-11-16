from fastapi.testclient import TestClient

from ai_os.api import app


def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_API_KEY", "test-owner-key")
    monkeypatch.setenv("AI_OS_DATABASE_URL", "sqlite:///" + str(tmp_path / "cinecode.db"))
    return TestClient(app)


def _headers():
    return {"X-API-Key": "test-owner-key"}


def test_cinecode_routes_require_owner_auth(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        assert client.get("/cinecode/status").status_code == 401
        assert client.get("/cinecode/jobs").status_code == 401
        assert client.post("/cinecode/jobs", json={"brief": "A sufficiently long film brief for this test.", "music_source": "none"}).status_code == 401


def test_cinecode_job_requires_owner_approval_before_execution(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        created = client.post("/cinecode/jobs", headers=_headers(), json={
            "brief": "Create a short cinematic film about a lighthouse in a storm.",
            "mode": "quick",
            "music_source": "none",
        })
        assert created.status_code == 201
        job = created.json()
        assert job["status"] == "pending_approval"
        assert job["approved_at"] is None
        assert "artifact_path" not in job

        approved = client.post(f"/cinecode/jobs/{job['id']}/approve", headers=_headers(), json={})
        assert approved.status_code == 200
        assert approved.json()["status"] == "approved"
        assert approved.json()["approved_at"]
        assert "waiting for an explicitly enabled local worker" in approved.json()["progress"]

        status = client.get("/cinecode/status", headers=_headers()).json()
        assert status["execution_enabled"] is False
        assert status["billing_confirmed"] is False
        assert status["publishing"].startswith("not integrated")


def test_cinecode_reject_and_cancel_transitions_are_bounded(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        rejected = client.post("/cinecode/jobs", headers=_headers(), json={
            "brief": "A short film brief long enough to satisfy the schema.", "music_source": "none"
        }).json()
        response = client.post(f"/cinecode/jobs/{rejected['id']}/reject", headers=_headers(), json={})
        assert response.status_code == 200
        assert response.json()["status"] == "rejected"
        assert client.post(f"/cinecode/jobs/{rejected['id']}/approve", headers=_headers(), json={}).status_code == 409

        queued = client.post("/cinecode/jobs", headers=_headers(), json={
            "brief": "Another short film brief long enough for the schema.", "music_source": "none"
        }).json()
        assert client.post(f"/cinecode/jobs/{queued['id']}/approve", headers=_headers(), json={}).status_code == 200
        cancelled = client.post(f"/cinecode/jobs/{queued['id']}/cancel", headers=_headers(), json={})
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        assert cancelled.json()["cancel_requested"] is True


def test_cinecode_artifact_is_unavailable_until_verified_completion(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        job = client.post("/cinecode/jobs", headers=_headers(), json={
            "brief": "A documentary-style short film about ocean conservation.", "music_source": "none"
        }).json()
        response = client.get(f"/cinecode/jobs/{job['id']}/artifact", headers=_headers())
        assert response.status_code == 409


def test_cinecode_worker_requires_both_explicit_execution_gates(monkeypatch):
    from ai_os import cinecode_worker

    monkeypatch.delenv("AI_OS_CINECODE_EXECUTION_ENABLED", raising=False)
    monkeypatch.delenv("AI_OS_CINECODE_BILLING_CONFIRMED", raising=False)
    assert cinecode_worker._enabled() is False
    monkeypatch.setenv("AI_OS_CINECODE_EXECUTION_ENABLED", "true")
    assert cinecode_worker._enabled() is False
    monkeypatch.setenv("AI_OS_CINECODE_BILLING_CONFIRMED", "true")
    assert cinecode_worker._enabled() is True


def test_owner_console_exposes_cinecode_studio_link():
    with TestClient(app) as client:
        response = client.get("/owner")
    assert response.status_code == 200
    assert 'href="/cinecode"' in response.text
    assert "Cinecode Studio" in response.text


def test_cinecode_requires_explicit_music_choice(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        response = client.post("/cinecode/jobs", headers=_headers(), json={
            "brief": "A short film brief that omits the music choice intentionally."
        })
        assert response.status_code == 422


def test_worker_readonly_kit_can_be_cleaned_up():
    from pathlib import Path
    from ai_os.cinecode_worker import _CleanupTemporaryDirectory, _make_read_only

    with _CleanupTemporaryDirectory(prefix="cinecode-test-") as temp:
        kit = Path(temp) / "cinecode-kit"
        nested = kit / "docs"
        nested.mkdir(parents=True)
        source_file = nested / "SKILL.md"
        source_file.write_text("reviewed instructions", encoding="utf-8")
        _make_read_only(kit)
        assert source_file.stat().st_mode & 0o222 == 0
        assert nested.stat().st_mode & 0o222 == 0
