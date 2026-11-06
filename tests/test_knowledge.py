from fastapi.testclient import TestClient

from ai_os.api import app


def _candidate_payload():
    return {
        "title": "International buyers prefer downloadable assets",
        "content": "A source reports increasing buyer interest in downloadable game assets.",
        "category": "market_research",
        "source_url": "https://example.com/research/downloadable-assets",
        "source_title": "Digital Asset Market Research",
        "source_published_at": "2026-10-20T00:00:00Z",
        "confidence": 0.65,
        "tags": ["gaming", "digital-products"],
    }


def test_knowledge_is_saved_as_candidate_with_source_provenance():
    with TestClient(app) as client:
        created = client.post("/knowledge", json=_candidate_payload())
        assert created.status_code == 201, created.text
        item = created.json()

        assert item["status"] == "candidate"
        assert item["source_url"].startswith("https://example.com/")
        assert item["source_title"] == "Digital Asset Market Research"
        assert item["source_accessed_at"]
        assert item["created_by"] == "local-development"
        assert item["reviewed_by"] is None
        assert item["tags"] == ["gaming", "digital-products"]

        listed = client.get("/knowledge", params={"status": "candidate"})
        detail = client.get(f"/knowledge/{item['id']}")

    assert listed.status_code == 200
    assert any(entry["id"] == item["id"] for entry in listed.json())
    assert detail.status_code == 200
    assert detail.json()["id"] == item["id"]


def test_knowledge_requires_explicit_review_before_becoming_accepted():
    with TestClient(app) as client:
        created = client.post("/knowledge", json=_candidate_payload())
        item_id = created.json()["id"]

        accepted = client.post(
            f"/knowledge/{item_id}/review",
            json={"decision": "accepted", "note": "Source checked by owner."},
        )
        repeated = client.post(
            f"/knowledge/{item_id}/review",
            json={"decision": "rejected", "note": "Attempt to change a final decision."},
        )
        accepted_list = client.get("/knowledge", params={"status": "accepted"})
        audit = client.get("/audit/verify")

    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"
    assert accepted.json()["reviewed_by"] == "local-development"
    assert accepted.json()["review_note"] == "Source checked by owner."
    assert repeated.status_code == 409
    assert any(entry["id"] == item_id for entry in accepted_list.json())
    assert audit.json()["valid"] is True


def test_knowledge_rejects_invalid_source_and_blank_content():
    with TestClient(app) as client:
        invalid_url = _candidate_payload()
        invalid_url["source_url"] = "javascript:alert(1)"
        invalid = client.post("/knowledge", json=invalid_url)

        blank_content = _candidate_payload()
        blank_content["content"] = "   "
        blank = client.post("/knowledge", json=blank_content)

    assert invalid.status_code == 422
    assert blank.status_code == 422


def test_knowledge_endpoints_require_owner_token_when_configured(monkeypatch):
    token = "test-owner-token-" + "x" * 40
    monkeypatch.setenv("AI_OS_ENV", "development")
    monkeypatch.setenv("AI_OS_API_TOKEN", token)
    with TestClient(app) as client:
        denied = client.get("/knowledge")
        allowed = client.get("/knowledge", headers={"Authorization": "Bearer " + token})
    assert denied.status_code == 401
    assert allowed.status_code == 200


def test_agent_retrieval_returns_only_relevant_owner_accepted_items():
    from ai_os.knowledge import retrieve_accepted_knowledge

    with TestClient(app) as client:
        candidate = client.post("/knowledge", json=_candidate_payload()).json()
        client.post(
            f"/knowledge/{candidate['id']}/review",
            json={"decision": "accepted", "note": "Checked by owner."},
        )
        rejected_payload = _candidate_payload()
        rejected_payload["title"] = "Rejected unrelated market note"
        rejected_payload["content"] = "Unrelated content about office furniture."
        rejected = client.post("/knowledge", json=rejected_payload).json()
        client.post(
            f"/knowledge/{rejected['id']}/review",
            json={"decision": "rejected", "note": "Not relevant."},
        )
        unreviewed_payload = _candidate_payload()
        unreviewed_payload["title"] = "Pending gaming market note"
        client.post("/knowledge", json=unreviewed_payload)

    retrieved = retrieve_accepted_knowledge("gaming downloadable digital products")
    assert [item["id"] for item in retrieved] == [candidate["id"]]
    assert retrieved[0]["status"] == "accepted"
