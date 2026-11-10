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



def test_finance_and_customer_records_are_business_scoped(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", "sqlite:///" + str(tmp_path / "business-records.db"))
    initialize_database()
    from ai_os import business_ops

    business_ops.create_record("customer", {"title": "Agency buyer", "business_id": "physical-agency"})
    business_ops.create_record("customer", {"title": "Own brand customer", "business_id": "physical-brand"})
    business_ops.create_record("revenue", {"title": "Agency order", "amount": 100, "verified_payment": True, "business_id": "physical-agency"})
    expense = business_ops.create_record("expense", {"title": "Agency packaging", "amount": 20, "business_id": "physical-agency"})
    business_ops.create_record("revenue", {"title": "Brand order", "amount": 300, "verified_payment": True, "business_id": "physical-brand"})

    assert [x["title"] for x in business_ops.list_records("customer", business_id="physical-agency")] == ["Agency buyer"]
    assert [x["title"] for x in business_ops.list_records("customer", business_id="physical-brand")] == ["Own brand customer"]
    assert business_ops.business_summary("physical-agency")["customers"] == 1
    assert business_ops.business_summary("physical-brand")["customers"] == 1
    assert business_ops.business_summary("physical-agency")["verified_revenue_by_currency"][0]["total"] == 100
    assert business_ops.business_summary("physical-brand")["verified_revenue_by_currency"][0]["total"] == 300
    assert expense["business_id"] == "physical-agency"
    with connect() as db:
        approval = db.execute("SELECT business_id FROM approvals WHERE id=?", (expense["approval_id"],)).fetchone()
    assert approval["business_id"] == "physical-agency"


def test_research_sources_are_retrieved_only_within_their_business(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", "sqlite:///" + str(tmp_path / "business-research.db"))
    initialize_database()
    from ai_os.research_sources import list_sources, research_context
    from datetime import datetime, timezone

    with connect() as db:
        db.execute("INSERT INTO research_sources (id,business_id,url,title,content,captured_at,content_type) VALUES (?,?,?,?,?,?,?)",
                   ("agency-source", "physical-agency", "https://example.com/agency", "Pink salt wholesale buyers", "Agency wholesale buyer research evidence.", datetime.now(timezone.utc).isoformat(), "text/plain"))
        db.execute("INSERT INTO research_sources (id,business_id,url,title,content,captured_at,content_type) VALUES (?,?,?,?,?,?,?)",
                   ("brand-source", "physical-brand", "https://example.com/brand", "Pink salt consumer brand", "Own brand consumer research evidence.", datetime.now(timezone.utc).isoformat(), "text/plain"))

    assert [x["id"] for x in list_sources(business_id="physical-agency")] == ["agency-source"]
    assert [x["id"] for x in list_sources(business_id="physical-brand")] == ["brand-source"]
    assert "agency-source" not in research_context("wholesale buyers", business_id="physical-brand")
    assert "agency-source" not in research_context("wholesale buyers", business_id="digital-products")
    assert "agency-source" in research_context("wholesale buyers", business_id="physical-agency")
