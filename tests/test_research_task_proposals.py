from fastapi.testclient import TestClient

import ai_os.research_planner as planner
from ai_os.api import app


def test_ceo_drafts_task_from_accepted_sources_and_owner_approval_creates_task(monkeypatch):
    def fake_generate(system_prompt, user_prompt):
        import json
        payload = json.loads(user_prompt)
        source = payload["accepted_sources"][0]
        return ({
            "proposals": [{
                "title": "Validate demand for downloadable game assets",
                "description": "Compare marketplace evidence and identify a low-cost product opportunity.",
                "department": "research",
                "source_ids": [source["id"]],
                "rationale": "The accepted source contains relevant market signals that warrant validation.",
            }]
        }, {"provider": "test-provider", "model": "test-model"})
    monkeypatch.setattr(planner, "generate_json", fake_generate)
    knowledge_payload = {
        "title": "Buyer interest in downloadable game assets",
        "content": "Accepted evidence indicates buyer interest in downloadable game assets.",
        "category": "market_research",
        "source_url": "https://example.com/game-assets-report",
        "source_title": "Game asset market report",
        "source_published_at": "2026-11-01T00:00:00Z",
        "tags": ["gaming", "digital-products"],
    }
    with TestClient(app) as client:
        created = client.post("/knowledge", json=knowledge_payload)
        assert created.status_code == 201, created.text
        source_id = created.json()["id"]
        reviewed = client.post(
            f"/knowledge/{source_id}/review",
            json={"decision": "accepted", "note": "Owner reviewed source."},
        )
        assert reviewed.status_code == 200
        draft = client.post("/research/task-proposals/draft")
        assert draft.status_code == 200, draft.text
        proposal = draft.json()["proposals"][0]
        listed = client.get("/research/task-proposals", params={"status": "candidate"})
        tasks_before = client.get("/tasks").json()
        decision = client.post(
            f"/research/task-proposals/{proposal['id']}/review",
            json={"decision": "approved", "note": "Approved for internal research."},
        )
        tasks_after = client.get("/tasks").json()
    assert draft.json()["created"] == 1
    assert proposal["source_ids"] == [source_id]
    assert any(row["id"] == proposal["id"] for row in listed.json())
    assert decision.status_code == 200, decision.text
    assert decision.json()["status"] == "approved"
    assert decision.json()["task_id"]
    assert len(tasks_after) == len(tasks_before) + 1
    assert tasks_after[0]["id"] == decision.json()["task_id"]
    assert tasks_after[0]["status"] == "queued"


def test_ceo_cannot_create_task_proposal_from_unaccepted_sources(monkeypatch):
    monkeypatch.setattr(planner, "generate_json", lambda *args: ({
        "proposals": [{
            "title": "Task from pending source",
            "description": "This must be rejected.",
            "department": "research",
            "source_ids": ["not-accepted-source-id"],
            "rationale": "A source should be accepted first.",
        }]
    }, {"provider": "test", "model": "test"}))
    with TestClient(app) as client:
        response = client.post("/research/task-proposals/draft")
    assert response.status_code == 200
    assert response.json()["created"] == 0
    assert response.json()["rejected"]


def test_task_proposal_cannot_be_approved_twice(monkeypatch):
    monkeypatch.setattr(planner, "generate_json", lambda *args: ({
        "proposals": []
    }, {"provider": "test", "model": "test"}))
    with TestClient(app) as client:
        # An unknown ID cannot be used to create a task.
        response = client.post(
            "/research/task-proposals/not-found/review",
            json={"decision": "approved"},
        )
    assert response.status_code == 404
