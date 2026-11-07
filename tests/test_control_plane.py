from fastapi.testclient import TestClient

from ai_os.api import app


def test_control_plane_seeds_profile_catalog_and_distinguishes_live_runtime():
    with TestClient(app) as client:
        status = client.get("/control-plane")
        agents = client.get("/control-plane/agents")

    assert status.status_code == 200
    assert status.json()["agent_profiles_registered"] >= 280
    assert status.json()["logical_agents_enabled"] >= 280
    assert status.json()["runtime_instances_registered"] == 0
    assert status.json()["runtime_status"] == "not_implemented_in_cp1"
    assert "not proof of live worker processes" in status.json()["notice"]
    assert agents.status_code == 200
    assert any(item["agent_id"] == "company-orchestrator" for item in agents.json()["agents"])
    assert any(item["agent_id"] == "research-synthesist" for item in agents.json()["agents"])


def test_control_plane_agent_detail_includes_ceo_reporting_relationship():
    with TestClient(app) as client:
        response = client.get("/control-plane/agents/research-synthesist")

    assert response.status_code == 200
    assert response.json()["department"] == "research"
    assert any(
        relation["target_agent_id"] == "company-orchestrator"
        and relation["relationship_type"] == "reports_to"
        for relation in response.json()["relationships"]
    )


def test_control_plane_agent_can_be_disabled_and_reenabled():
    with TestClient(app) as client:
        disabled = client.patch(
            "/control-plane/agents/research-synthesist",
            json={"enabled": False},
        )
        enabled = client.patch(
            "/control-plane/agents/research-synthesist",
            json={"enabled": True},
        )

    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True


def test_control_plane_endpoint_registration_is_disabled_by_default():
    with TestClient(app) as client:
        created = client.post(
            "/control-plane/endpoints",
            json={"name": "Local test model", "protocol": "openai_compatible",
                  "base_url": "http://localhost:1234/v1"},
        )
        endpoints = client.get("/control-plane/endpoints")

    assert created.status_code == 201
    assert created.json()["enabled"] is False
    assert created.json()["protocol"] == "openai_compatible"
    assert any(x["endpoint_id"] == created.json()["endpoint_id"] for x in endpoints.json()["endpoints"])
    assert "does not connect" in endpoints.json()["notice"]


def test_control_plane_rejects_non_https_remote_endpoint():
    with TestClient(app) as client:
        response = client.post(
            "/control-plane/endpoints",
            json={"name": "Unsafe remote", "protocol": "mcp",
                  "base_url": "http://example.com/mcp"},
        )

    assert response.status_code == 422


def test_control_plane_rejects_credentials_embedded_in_endpoint_url():
    with TestClient(app) as client:
        response = client.post(
            "/control-plane/endpoints",
            json={"name": "Credential URL", "protocol": "mcp",
                  "base_url": "https://user:password@example.com/mcp"},
        )

    assert response.status_code == 422


def test_control_plane_rejects_secret_like_metadata_keys():
    with TestClient(app) as client:
        response = client.post(
            "/control-plane/endpoints",
            json={"name": "Bad metadata", "protocol": "internal",
                  "metadata": {"api_key": "do-not-store"}},
        )

    assert response.status_code == 422


def test_control_plane_endpoint_requires_url_for_network_protocols():
    with TestClient(app) as client:
        response = client.post(
            "/control-plane/endpoints",
            json={"name": "Missing URL", "protocol": "a2a"},
        )

    assert response.status_code == 422


def test_control_plane_routes_require_owner_token_when_configured(monkeypatch):
    monkeypatch.setenv("AI_OS_API_TOKEN", "t" * 40)
    with TestClient(app) as client:
        denied = client.get("/control-plane")
        allowed = client.get("/control-plane", headers={"Authorization": "Bearer " + "t" * 40})

    assert denied.status_code == 401
    assert allowed.status_code == 200


def test_control_plane_ceo_agent_cannot_be_disabled():
    with TestClient(app) as client:
        response = client.patch(
            "/control-plane/agents/company-orchestrator",
            json={"enabled": False},
        )

    assert response.status_code == 409
    assert "cannot be disabled" in response.json()["detail"]


def test_control_plane_rejects_raw_credential_values():
    with TestClient(app) as client:
        response = client.post(
            "/control-plane/endpoints",
            json={"name": "Unsafe credential", "protocol": "mcp",
                  "base_url": "https://example.com/mcp",
                  "credential_ref": "sk-live-this-is-not-a-reference"},
        )

    assert response.status_code == 422


def test_control_plane_rejects_unrecognized_endpoint_metadata():
    with TestClient(app) as client:
        response = client.post(
            "/control-plane/endpoints",
            json={"name": "Metadata", "protocol": "internal",
                  "metadata": {"description": "anything"}},
        )

    assert response.status_code == 422
