from fastapi.testclient import TestClient

from opencompany_app.api import app, get_runtime
from opencompany_app.runtime import create_runtime


def test_owner_brain_memory_proposal_review_and_scope(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCOMPANY_OWNER_API_KEY", "test-owner-key")
    runtime = create_runtime(str(tmp_path / "brain-api.sqlite3"))
    app.dependency_overrides[get_runtime] = lambda: runtime
    try:
        with TestClient(app, base_url="https://testserver") as client:
            headers = {"X-OpenCompany-API-Key": "test-owner-key"}
            proposed = client.post("/brain/memories", headers=headers, json={
                "scope": "business:physical-agency",
                "topic": "Supplier checks",
                "content": "Verify manufacturer capacity with independent evidence",
                "source": "owner",
                "confidence": 0.9,
            })
            assert proposed.status_code == 200
            memory_id = proposed.json()["id"]
            assert proposed.json()["approval"] == "proposed"

            pending = client.get("/brain/memories?approval=proposed", headers=headers)
            assert pending.status_code == 200
            assert any(item["id"] == memory_id for item in pending.json()["memories"])

            decision = client.post(
                f"/brain/memories/{memory_id}/decision", headers=headers,
                json={"approve": True, "note": "Reviewed by owner"},
            )
            assert decision.status_code == 200
            assert decision.json()["approval"] == "approved"

            approved = client.get(
                "/brain/memories?approval=approved&scope=business%3Aphysical-agency",
                headers=headers,
            )
            assert approved.status_code == 200
            assert [item["id"] for item in approved.json()["memories"]] == [memory_id]

            repeated = client.post(
                f"/brain/memories/{memory_id}/decision", headers=headers,
                json={"approve": False},
            )
            assert repeated.status_code == 404
    finally:
        app.dependency_overrides.clear()
        runtime.close()


def test_brain_memory_api_rejects_invalid_scope_and_unauthenticated_access(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCOMPANY_OWNER_API_KEY", "test-owner-key")
    runtime = create_runtime(str(tmp_path / "brain-api-security.sqlite3"))
    app.dependency_overrides[get_runtime] = lambda: runtime
    try:
        with TestClient(app, base_url="https://testserver") as client:
            unauthenticated = client.post("/brain/memories", json={
                "scope": "company", "topic": "t", "content": "c",
            })
            assert unauthenticated.status_code == 401

            invalid = client.post(
                "/brain/memories",
                headers={"X-OpenCompany-API-Key": "test-owner-key"},
                json={"scope": "global-everywhere", "topic": "t", "content": "c"},
            )
            assert invalid.status_code == 422
    finally:
        app.dependency_overrides.clear()
        runtime.close()
