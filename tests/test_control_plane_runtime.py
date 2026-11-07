from fastapi.testclient import TestClient

from ai_os.api import app


def _register_worker(client):
    response = client.post(
        "/control-plane/runtimes",
        json={"runtime_name": "Test worker", "runtime_kind": "worker"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_runtime_registration_returns_one_time_token_and_safe_public_record():
    with TestClient(app) as client:
        created = _register_worker(client)
        listed = client.get("/control-plane/runtimes")

    runtime = created["runtime"]
    assert runtime["runtime_kind"] == "worker"
    assert runtime["health"] == "offline"
    assert runtime["last_heartbeat_at"] is None
    assert "token_hash" not in runtime
    assert len(created["runtime_token"]) >= 48
    assert any(item["runtime_id"] == runtime["runtime_id"] for item in listed.json()["runtimes"])
    assert "runtime_token" not in listed.text


def test_runtime_heartbeat_requires_its_registered_credential():
    with TestClient(app) as client:
        created = _register_worker(client)
        payload = {"runtime_id": created["runtime"]["runtime_id"], "status": "idle"}
        missing = client.post("/control-plane/runtime-heartbeat", json=payload)
        wrong = client.post(
            "/control-plane/runtime-heartbeat", json=payload,
            headers={"X-AI-Runtime-Token": "x" * 64},
        )
        accepted = client.post(
            "/control-plane/runtime-heartbeat", json=payload,
            headers={"X-AI-Runtime-Token": created["runtime_token"]},
        )

    assert missing.status_code == 401
    assert wrong.status_code == 403
    assert accepted.status_code == 200
    assert accepted.json()["health"] == "idle"
    assert accepted.json()["last_heartbeat_at"]


def test_runtime_heartbeat_can_report_current_job_without_exposing_token():
    with TestClient(app) as client:
        created = _register_worker(client)
        response = client.post(
            "/control-plane/runtime-heartbeat",
            json={"runtime_id": created["runtime"]["runtime_id"],
                  "status": "working", "current_job_id": "job-123"},
            headers={"X-AI-Runtime-Token": created["runtime_token"]},
        )

    assert response.status_code == 200
    assert response.json()["current_job_id"] == "job-123"
    assert "token_hash" not in response.json()


def test_runtime_token_rotation_invalidates_previous_credential():
    with TestClient(app) as client:
        created = _register_worker(client)
        runtime_id = created["runtime"]["runtime_id"]
        rotated = client.post(f"/control-plane/runtimes/{runtime_id}/rotate-token")
        payload = {"runtime_id": runtime_id, "status": "idle"}
        old_token = client.post(
            "/control-plane/runtime-heartbeat", json=payload,
            headers={"X-AI-Runtime-Token": created["runtime_token"]},
        )
        new_token = client.post(
            "/control-plane/runtime-heartbeat", json=payload,
            headers={"X-AI-Runtime-Token": rotated.json()["runtime_token"]},
        )

    assert rotated.status_code == 200
    assert old_token.status_code == 403
    assert new_token.status_code == 200


def test_revoked_runtime_cannot_send_heartbeats():
    with TestClient(app) as client:
        created = _register_worker(client)
        runtime_id = created["runtime"]["runtime_id"]
        revoked = client.post(f"/control-plane/runtimes/{runtime_id}/revoke")
        heartbeat = client.post(
            "/control-plane/runtime-heartbeat",
            json={"runtime_id": runtime_id, "status": "idle"},
            headers={"X-AI-Runtime-Token": created["runtime_token"]},
        )
        detail = client.get(f"/control-plane/runtimes/{runtime_id}")

    assert revoked.status_code == 200
    assert revoked.json()["health"] == "revoked"
    assert heartbeat.status_code == 403
    assert detail.json()["revoked"] is True


def test_agent_runtime_requires_an_enabled_registered_agent():
    with TestClient(app) as client:
        missing = client.post(
            "/control-plane/runtimes",
            json={"runtime_name": "Missing agent", "runtime_kind": "agent"},
        )
        created = client.post(
            "/control-plane/runtimes",
            json={"runtime_name": "Research specialist", "runtime_kind": "agent",
                  "agent_id": "research-synthesist"},
        )
        invalid_worker = client.post(
            "/control-plane/runtimes",
            json={"runtime_name": "Worker with agent identity", "runtime_kind": "worker",
                  "agent_id": "research-synthesist"},
        )

    assert missing.status_code == 422
    assert created.status_code == 201
    assert created.json()["runtime"]["agent_id"] == "research-synthesist"
    assert invalid_worker.status_code == 422


def test_control_plane_overview_counts_runtime_instances():
    with TestClient(app) as client:
        _register_worker(client)
        overview = client.get("/control-plane")

    assert overview.status_code == 200
    assert overview.json()["runtime_instances_registered"] >= 1


def test_runtime_without_recent_heartbeat_is_reported_stale():
    from ai_os.db import connect

    with TestClient(app) as client:
        created = _register_worker(client)
        runtime_id = created["runtime"]["runtime_id"]
        with connect() as db:
            db.execute(
                "UPDATE control_plane_runtime_instances SET last_heartbeat_at=? WHERE runtime_id=?",
                ("2000-01-01T00:00:00+00:00", runtime_id),
            )
        response = client.get(f"/control-plane/runtimes/{runtime_id}")

    assert response.status_code == 200
    assert response.json()["health"] == "stale"


def test_disabling_logical_agent_revokes_its_runtime_credential():
    with TestClient(app) as client:
        created = client.post(
            "/control-plane/runtimes",
            json={"runtime_name": "Research runtime", "runtime_kind": "agent",
                  "agent_id": "research-synthesist"},
        )
        runtime_id = created.json()["runtime"]["runtime_id"]
        disabled = client.patch(
            "/control-plane/agents/research-synthesist",
            json={"enabled": False},
        )
        heartbeat = client.post(
            "/control-plane/runtime-heartbeat",
            json={"runtime_id": runtime_id, "status": "idle"},
            headers={"X-AI-Runtime-Token": created.json()["runtime_token"]},
        )
        reenabled = client.patch(
            "/control-plane/agents/research-synthesist",
            json={"enabled": True},
        )

    assert created.status_code == 201
    assert disabled.status_code == 200
    assert heartbeat.status_code == 403
    assert reenabled.status_code == 200


def test_expired_runtime_credential_is_rejected_and_owner_can_rotate_it():
    from ai_os.db import connect

    with TestClient(app) as client:
        created = _register_worker(client)
        runtime_id = created["runtime"]["runtime_id"]
        with connect() as db:
            db.execute(
                "UPDATE control_plane_runtime_instances SET token_expires_at=? WHERE runtime_id=?",
                ("2000-01-01T00:00:00+00:00", runtime_id),
            )
        payload = {"runtime_id": runtime_id, "status": "idle"}
        expired = client.post(
            "/control-plane/runtime-heartbeat", json=payload,
            headers={"X-AI-Runtime-Token": created["runtime_token"]},
        )
        rotated = client.post(f"/control-plane/runtimes/{runtime_id}/rotate-token")
        accepted = client.post(
            "/control-plane/runtime-heartbeat", json=payload,
            headers={"X-AI-Runtime-Token": rotated.json()["runtime_token"]},
        )

    assert expired.status_code == 403
    assert "expired" in expired.json()["detail"]
    assert rotated.status_code == 200
    assert accepted.status_code == 200
