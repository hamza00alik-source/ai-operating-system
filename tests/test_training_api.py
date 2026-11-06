from fastapi.testclient import TestClient

from ai_os.api import app


def _setup(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'training-api.sqlite3'}")
    token = "training-owner-token-" + "x" * 40
    monkeypatch.setenv("AI_OS_API_TOKEN", token)
    monkeypatch.setenv("AI_OS_ENV", "production")
    return {"Authorization": "Bearer " + token}


def _payload():
    return {
        "task_family": "research synthesis",
        "system_prompt": "You are a careful research analyst.",
        "user_input": "Summarize the supplied official release note.",
        "ideal_response": "The release added CSV export. Evidence: https://example.test/changelog",
        "source_refs": ["https://example.test/changelog"],
        "rights_confirmed": True,
        "privacy_reviewed": True,
    }


def test_owner_training_curation_review_and_dataset_export(tmp_path, monkeypatch):
    headers = _setup(monkeypatch, tmp_path)
    with TestClient(app) as client:
        assert client.get("/training-examples").status_code == 401
        created = client.post("/training-examples", json=_payload(), headers=headers)
        assert created.status_code == 201
        item = created.json()
        assert item["status"] == "candidate"

        no_export = client.post("/training-datasets/export", json={}, headers=headers)
        assert no_export.status_code == 409

        accepted = client.post(
            f"/training-examples/{item['id']}/review",
            json={"decision": "accepted", "note": "Rights and privacy checked."},
            headers=headers,
        )
        assert accepted.status_code == 200
        assert accepted.json()["status"] == "accepted"

        exported = client.post("/training-datasets/export", json={"limit": 100}, headers=headers)
        assert exported.status_code == 201
        assert exported.json()["example_count"] == 1
        assert exported.json()["format"] == "chat_messages_jsonl_with_metadata"
        history = client.get("/training-datasets/exports", headers=headers)
        assert history.status_code == 200
        assert history.json()[0]["dataset_sha256"] == exported.json()["dataset_sha256"]


def test_training_candidate_requires_rights_privacy_and_owner_auth(tmp_path, monkeypatch):
    headers = _setup(monkeypatch, tmp_path)
    with TestClient(app) as client:
        denied = client.post("/training-examples", json=_payload())
        assert denied.status_code == 401
        invalid = _payload()
        invalid["rights_confirmed"] = False
        rejected = client.post("/training-examples", json=invalid, headers=headers)
        assert rejected.status_code == 422


def test_owner_dashboard_exposes_training_data_review_and_export_controls():
    with TestClient(app) as client:
        page = client.get("/dashboard")
    assert page.status_code == 200
    assert 'api("/training-examples?status=candidate&limit=20")' in page.text
    assert "Save training candidate" in page.text
    assert "Accept for training" in page.text
    assert "Export accepted dataset" in page.text
    assert "This export does not train a model." in page.text
