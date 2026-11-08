"""End-to-end contract test for the real OpenAI-compatible adapter path.

The HTTP transport is stubbed at the network boundary, while the application,
durable queue, specialist runtime, JSON parser and report persistence all run.
This proves integration wiring, not live provider availability.
"""
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from ai_os.api import app


def test_company_workflow_uses_model_adapter_and_passes_dependency_handoff(monkeypatch):
    monkeypatch.setenv("AI_OS_AGENT_SIGNING_KEY", "integration-test-signing-key-" + "x" * 40)
    monkeypatch.setenv("AI_OS_MODEL_ENABLED", "true")
    monkeypatch.setenv("AI_OS_MODEL_BACKEND", "openai_compatible")
    monkeypatch.setenv("AI_OS_MODEL_PROVIDER", "integration-test-provider")
    monkeypatch.setenv("AI_OS_MODEL_BASE_URL", "https://model.example/v1")
    monkeypatch.setenv("AI_OS_MODEL_NAME", "integration-test-model")
    monkeypatch.delenv("AI_OS_MODEL_API_KEY", raising=False)

    requests = []

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request, timeout):
        body = json.loads(request.data.decode("utf-8"))
        requests.append(body)
        report = {
            "status": "completed",
            "summary": f"Adapter-backed specialist report {len(requests)}",
            "evidence": ["The response passed through the OpenAI-compatible JSON adapter."],
            "blockers": [],
            "knowledge_candidates": [],
        }
        return FakeResponse({
            "choices": [{"message": {"content": json.dumps(report)}}]
        })

    monkeypatch.setattr("ai_os.model_adapter.urllib.request.urlopen", fake_urlopen)

    payload = {
        "title": "Model adapter integration test",
        "description": "Verify actual adapter wiring and automatic report handoff.",
        "steps": [
            {
                "step_key": "research",
                "agent_id": "product-trend-researcher",
                "task": "Research customer demand",
            },
            {
                "step_key": "strategy",
                "agent_id": "business-strategist",
                "task": "Recommend a product using the research report",
                "depends_on": ["research"],
            },
        ],
    }

    with TestClient(app) as client:
        created = client.post("/company-runs", json=payload)
        assert created.status_code == 201, created.text
        run_id = created.json()["id"]

        first = client.post("/worker/run-once")
        assert first.status_code == 200, first.text
        assert first.json()["job"]["status"] == "completed"

        middle = client.get(f"/company-runs/{run_id}").json()
        assert middle["steps"][0]["status"] == "completed"
        assert middle["steps"][1]["status"] == "pending"

        second = client.post("/worker/run-once")
        assert second.status_code == 200, second.text
        assert second.json()["job"]["status"] == "completed"

        # The next worker cycle automatically schedules and executes the CEO review.
        third = client.post("/worker/run-once")
        assert third.status_code == 200, third.text
        assert third.json()["job"]["status"] == "completed"
        assert third.json()["job"]["job_type"] == "review_company_run"

        final = client.get(f"/company-runs/{run_id}").json()

    assert len(requests) == 3
    assert all(request["model"] == "integration-test-model" for request in requests)
    assert "Adapter-backed specialist report 1" in requests[1]["messages"][1]["content"]
    assert "Adapter-backed specialist report 1" in requests[2]["messages"][1]["content"]
    assert "Adapter-backed specialist report 2" in requests[2]["messages"][1]["content"]
    assert final["status"] == "completed"
    assert [step["status"] for step in final["steps"]] == ["completed", "completed"]
    assert final["steps"][1]["report"]["reported_to"] == "company-orchestrator"
