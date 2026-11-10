from fastapi.testclient import TestClient

from ai_os.api import app
from ai_os.brain import record_experience, retrieve_memories, review_memory, list_memories
from ai_os.db import initialize_database


def test_business_memories_are_strictly_isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", "sqlite:///" + str(tmp_path / "business-brains.db"))
    initialize_database()

    record_experience("agency-run", "agency-task", "sales", "Wholesale buyer qualification",
                      "Agency-only buyer qualification lesson.", business_id="physical-agency")
    record_experience("brand-run", "brand-task", "sales", "Own-brand customer retention strategy",
                      "Own-brand customer retention lesson.", business_id="physical-brand")
    record_experience("digital-run", "digital-task", "marketing", "Digital downloadable product positioning",
                      "Digital product launch lesson.", business_id="digital-products")

    agency_memory = list_memories("proposed", business_id="physical-agency")
    assert len(agency_memory) == 1
    assert agency_memory[0]["business_id"] == "physical-agency"
    assert len(list_memories("proposed", business_id="physical-brand")) == 1
    assert len(list_memories("proposed", business_id="digital-products")) == 1

    review_memory(agency_memory[0]["id"], "approved", "Owner approved")
    assert len(retrieve_memories("wholesale buyer qualification", "sales", business_id="physical-agency")) == 1
    assert retrieve_memories("wholesale buyer qualification", "sales", business_id="physical-brand") == []
    assert retrieve_memories("wholesale buyer qualification", "sales", business_id="digital-products") == []


def test_tasks_are_assigned_to_one_business_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", "sqlite:///" + str(tmp_path / "business-tasks.db"))
    with TestClient(app) as client:
        environments = client.get("/business-environments")
        assert environments.status_code == 200
        ids = {item["id"] for item in environments.json()["environments"]}
        assert {"physical-agency", "physical-brand", "digital-products"} <= ids

        task = client.post("/tasks", json={
            "title": "Research wholesale salt buyers",
            "department": "sales",
            "business_id": "physical-agency",
        })
        assert task.status_code == 201
        assert task.json()["business_id"] == "physical-agency"

        invalid = client.post("/tasks", json={
            "title": "Invalid environment task",
            "business_id": "all-businesses",
        })
        assert invalid.status_code == 422

        agency_status = client.get("/brain/status?business_id=physical-agency")
        brand_status = client.get("/brain/status?business_id=physical-brand")
        assert agency_status.status_code == brand_status.status_code == 200
        assert agency_status.json()["business_id"] == "physical-agency"
        assert brand_status.json()["business_id"] == "physical-brand"
