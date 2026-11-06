from fastapi.testclient import TestClient

from ai_os.api import app


def test_owner_only_knowledge_is_not_retrieved_by_agents():
    from ai_os.knowledge import retrieve_accepted_knowledge

    payload = {
        "title": "zzowneronlysecret operational note",
        "content": "zzowneronlysecret is a private owner-only instruction.",
        "category": "operations",
        "access_scope": "owner_only",
        "source_url": "https://example.com/owner-only-note",
        "source_title": "Owner private note",
        "confidence": 1.0,
        "tags": ["zzowneronlysecret"],
    }
    with TestClient(app) as client:
        created = client.post("/knowledge", json=payload)
        assert created.status_code == 201, created.text
        item = created.json()
        assert item["access_scope"] == "owner_only"
        reviewed = client.post(
            f"/knowledge/{item['id']}/review",
            json={"decision": "accepted", "note": "Owner-only material."},
        )
        assert reviewed.status_code == 200
        owner_list = client.get("/knowledge", params={"status": "accepted"})
        assert any(row["id"] == item["id"] for row in owner_list.json())

    assert retrieve_accepted_knowledge("zzowneronlysecret") == []
