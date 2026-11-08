from fastapi.testclient import TestClient

from ai_os.api import app


def test_agent_can_claim_task_and_share_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_OS_ENV", "development")
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'coordination.db'}")

    with TestClient(app) as client:
        registered = client.post("/agents/register", json={
            "agent_id": "researcher-1",
            "name": "Researcher",
            "role": "research",
        })
        assert registered.status_code == 201
        assert registered.json()["status"] == "active"

        task = client.post("/tasks", json={
            "title": "Research customer demand",
            "department": "research",
        })
        assert task.status_code == 201
        task_id = task.json()["id"]

        claimed = client.post("/agents/researcher-1/claim")
        assert claimed.status_code == 200
        assert claimed.json()["id"] == task_id
        assert claimed.json()["status"] == "running"
        assert claimed.json()["assigned_agent"] == "researcher-1"

        memory = client.post("/memory", json={
            "key": "customer_demand",
            "content": "Players report difficulty comparing compatible add-ons.",
            "source": "approved research task",
            "created_by": "researcher-1",
        })
        assert memory.status_code == 201
        assert memory.json()["key"] == "customer_demand"

        found = client.get("/memory", params={"q": "compatible"})
        assert found.status_code == 200
        assert len(found.json()) == 1
        assert found.json()[0]["created_by"] == "researcher-1"

        events = client.get("/audit")
        assert events.status_code == 200
        event_types = {event["event_type"] for event in events.json()}
        assert {"agent_registered", "task_claimed", "memory_written"} <= event_types


def test_unregistered_agent_cannot_claim_tasks(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_OS_ENV", "development")
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'empty.db'}")

    with TestClient(app) as client:
        response = client.post("/agents/not-registered/claim")
    assert response.status_code == 404
