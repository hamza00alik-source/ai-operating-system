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
    assert status.json()["runtime_status"] == "heartbeat_based"
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



def test_disabled_control_plane_agent_cannot_receive_work_packet_or_identity(monkeypatch):
    from ai_os.identity import AgentIdentityError, issue_agent_token
    from ai_os.work_packets import build_work_packet

    monkeypatch.setenv("AI_OS_AGENT_SIGNING_KEY", "k" * 48)
    with TestClient(app) as client:
        disabled = client.patch(
            "/control-plane/agents/research-synthesist",
            json={"enabled": False},
        )
        assert disabled.status_code == 200
        try:
            try:
                build_work_packet("research-synthesist", "Research market demand")
                assert False, "disabled agent unexpectedly received a work packet"
            except LookupError:
                pass
            try:
                issue_agent_token(
                    "research-synthesist",
                    run_id="run-disabled-agent",
                    capabilities=["step.report"],
                )
                assert False, "disabled agent unexpectedly received an identity"
            except AgentIdentityError:
                pass
        finally:
            client.patch(
                "/control-plane/agents/research-synthesist",
                json={"enabled": True},
            )


def test_disabled_control_plane_agent_cannot_be_assigned_to_new_company_run():
    from ai_os.execution import _validate_graph
    from ai_os.execution_schemas import CompanyRunCreate

    with TestClient(app) as client:
        disabled = client.patch(
            "/control-plane/agents/research-synthesist",
            json={"enabled": False},
        )
        assert disabled.status_code == 200
        try:
            payload = CompanyRunCreate(
                title="Disabled agent guard",
                description="A disabled logical agent must not receive new work.",
                steps=[{
                    "step_key": "research",
                    "agent_id": "research-synthesist",
                    "task": "Research a topic",
                    "context": "",
                    "depends_on": [],
                }],
            )
            try:
                _validate_graph(payload)
                assert False, "disabled agent unexpectedly passed assignment validation"
            except ValueError as exc:
                assert "enabled specialist" in str(exc)
        finally:
            client.patch(
                "/control-plane/agents/research-synthesist",
                json={"enabled": True},
            )



def test_control_plane_capabilities_are_deny_by_default_and_owner_grantable():
    with TestClient(app) as client:
        denied = client.post(
            "/control-plane/capabilities/evaluate",
            json={"agent_id": "research-synthesist", "capability": "tool.research.read",
                  "department_scope": "research"},
        )
        assert denied.status_code == 200
        assert denied.json()["allowed"] is False
        assert denied.json()["decision"] == "blocked_no_capability_grant"

        granted = client.post(
            "/control-plane/capabilities",
            json={"agent_id": "research-synthesist", "capability": "tool.research.read",
                  "department_scope": "research"},
        )
        assert granted.status_code == 201
        assert granted.json()["capability"] == "tool.research.read"

        allowed = client.post(
            "/control-plane/capabilities/evaluate",
            json={"agent_id": "research-synthesist", "capability": "tool.research.read",
                  "department_scope": "research"},
        )
        revoked = client.delete(
            "/control-plane/capabilities/" + granted.json()["grant_id"],
        )
        denied_again = client.post(
            "/control-plane/capabilities/evaluate",
            json={"agent_id": "research-synthesist", "capability": "tool.research.read",
                  "department_scope": "research"},
        )

    assert allowed.json()["allowed"] is True
    assert revoked.status_code == 200
    assert revoked.json()["revoked"] is True
    assert denied_again.json()["allowed"] is False


def test_department_manager_broker_route_is_scoped_and_audited():
    with TestClient(app) as client:
        manager_id = "research-synthesist"
        grants = client.get("/control-plane/capabilities", params={"agent_id": manager_id})
        allowed = client.post(
            "/control-plane/broker/evaluate",
            json={"source_agent_id": "company-orchestrator", "target_agent_id": manager_id},
        )
        denied = client.post(
            "/control-plane/broker/evaluate",
            json={"source_agent_id": manager_id, "target_agent_id": "product-trend-researcher"},
        )
        self_route = client.post(
            "/control-plane/broker/evaluate",
            json={"source_agent_id": manager_id, "target_agent_id": manager_id},
        )

    assert any(item["capability"] == "task.delegate"
               and item["department_scope"] == "research" for item in grants.json()["grants"])
    assert allowed.status_code == 200
    assert allowed.json()["allowed"] is True
    assert allowed.json()["decision"] == "allowed_ceo_route"
    assert denied.json()["allowed"] is False
    assert denied.json()["decision"] == "blocked_department_scope"
    assert self_route.json()["allowed"] is False
    assert self_route.json()["decision"] == "blocked_self_route"



def test_control_plane_database_errors_do_not_fall_back_to_registry_allowance(monkeypatch):
    import sqlite3
    from ai_os import control_plane

    def unavailable_database():
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(control_plane, "connect", unavailable_database)
    try:
        control_plane.is_control_plane_agent_enabled(
            "research-synthesist", fallback_enabled=True
        )
        assert False, "database failure must not permit registry-only fallback"
    except sqlite3.OperationalError as exc:
        assert "unable to open database" in str(exc)



def test_mcp_endpoint_owner_lifecycle_is_explicit_and_does_not_connect():
    with TestClient(app) as client:
        created = client.post(
            "/control-plane/endpoints",
            json={"name": "Approved MCP metadata", "protocol": "mcp",
                  "base_url": "https://mcp.example.org/mcp"},
        )
        endpoint_id = created.json()["endpoint_id"]
        enabled = client.patch(
            f"/control-plane/endpoints/{endpoint_id}", json={"enabled": True}
        )
        disabled = client.patch(
            f"/control-plane/endpoints/{endpoint_id}", json={"enabled": False}
        )

    assert created.status_code == 201
    assert created.json()["enabled"] is False
    assert enabled.status_code == 200
    assert enabled.json()["endpoint"]["enabled"] is True
    assert "no network connection" in enabled.json()["notice"]
    assert disabled.status_code == 200
    assert disabled.json()["endpoint"]["enabled"] is False


def test_mcp_endpoint_activation_requires_resolvable_env_credential(monkeypatch):
    with TestClient(app) as client:
        created = client.post(
            "/control-plane/endpoints",
            json={"name": "Authenticated MCP", "protocol": "mcp",
                  "base_url": "https://mcp.example.org/mcp",
                  "credential_ref": "env:AI_OS_TEST_MCP_TOKEN"},
        )
        endpoint_id = created.json()["endpoint_id"]
        missing = client.patch(
            f"/control-plane/endpoints/{endpoint_id}", json={"enabled": True}
        )
        monkeypatch.setenv("AI_OS_TEST_MCP_TOKEN", "test-secret-value")
        enabled = client.patch(
            f"/control-plane/endpoints/{endpoint_id}", json={"enabled": True}
        )

    assert missing.status_code == 422
    assert "not configured" in missing.json()["detail"]
    assert enabled.status_code == 200
    assert "test-secret-value" not in enabled.text


def test_a2a_endpoint_cannot_be_enabled_before_cp4_mcp_is_complete():
    with TestClient(app) as client:
        created = client.post(
            "/control-plane/endpoints",
            json={"name": "A2A pending", "protocol": "a2a",
                  "base_url": "https://a2a.example.org/agent"},
        )
        response = client.patch(
            f"/control-plane/endpoints/{created.json()['endpoint_id']}",
            json={"enabled": True},
        )

    assert response.status_code == 422
    assert "Only MCP endpoints" in response.json()["detail"]


def test_mcp_endpoint_secret_manager_reference_fails_closed():
    with TestClient(app) as client:
        created = client.post(
            "/control-plane/endpoints",
            json={"name": "Unresolved secret manager", "protocol": "mcp",
                  "base_url": "https://mcp.example.org/mcp",
                  "credential_ref": "secret://provider/secret"},
        )
        response = client.patch(
            f"/control-plane/endpoints/{created.json()['endpoint_id']}",
            json={"enabled": True},
        )

    assert response.status_code == 422
    assert "no secret-manager resolver" in response.json()["detail"]


def test_control_plane_accepts_encrypted_vault_reference_but_not_arbitrary_vault_text():
    with TestClient(app) as client:
        accepted = client.post(
            "/control-plane/endpoints",
            json={"name": "Vault-backed MCP", "protocol": "mcp",
                  "base_url": "https://mcp.example.org/mcp",
                  "credential_ref": "vault:123e4567-e89b-12d3-a456-426614174000"},
        )
        rejected = client.post(
            "/control-plane/endpoints",
            json={"name": "Malformed vault ref", "protocol": "mcp",
                  "base_url": "https://mcp.example.org/mcp",
                  "credential_ref": "vault:not-a-uuid"},
        )

    assert accepted.status_code == 201
    assert accepted.json()["credential_ref"] == "vault:123e4567-e89b-12d3-a456-426614174000"
    assert rejected.status_code == 422



def test_mcp_tool_mapping_requires_owner_confirmation_and_prior_discovery(monkeypatch):
    from ai_os import api

    monkeypatch.setattr(api, "discover_mcp_tools", lambda endpoint_id: {
        "endpoint_id": endpoint_id,
        "discovered_tool_count": 1,
        "tools": [{
            "name": "search_docs",
            "description": "Search public documentation",
            "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
            "trust": "untrusted_remote_metadata",
            "executable": False,
        }],
    })
    with TestClient(app) as client:
        endpoint = client.post(
            "/control-plane/endpoints",
            json={"name": "Read-only MCP test", "protocol": "mcp",
                  "base_url": "https://mcp.example.org/mcp"},
        )
        endpoint_id = endpoint.json()["endpoint_id"]
        enabled = client.patch(
            f"/control-plane/endpoints/{endpoint_id}", json={"enabled": True}
        )
        assert enabled.status_code == 200

        missing_discovery = client.post(
            "/control-plane/mcp/mappings",
            json={"endpoint_id": endpoint_id, "tool_name": "not_discovered",
                  "owner_confirmed_read_only": True},
        )
        assert missing_discovery.status_code == 422

        not_confirmed = client.post(
            "/control-plane/mcp/mappings",
            json={"endpoint_id": endpoint_id, "tool_name": "search_docs",
                  "owner_confirmed_read_only": False},
        )
        assert not_confirmed.status_code == 422

        discovered = client.post(f"/control-plane/endpoints/{endpoint_id}/discover")
        assert discovered.status_code == 200
        assert discovered.json()["execution_enabled"] is False

        approved = client.post(
            "/control-plane/mcp/mappings",
            json={"endpoint_id": endpoint_id, "tool_name": "search_docs",
                  "owner_confirmed_read_only": True},
        )

    assert approved.status_code == 201
    assert approved.json()["access_mode"] == "read_only"
    assert approved.json()["enabled"] is True
    assert approved.json()["executable"] is True


def test_mcp_tool_execution_requires_explicit_agent_capability_and_uses_broker(monkeypatch):
    from ai_os import api

    monkeypatch.setattr(api, "discover_mcp_tools", lambda endpoint_id: {
        "endpoint_id": endpoint_id,
        "discovered_tool_count": 1,
        "tools": [{
            "name": "search_docs", "description": "Read-only search",
            "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
            "trust": "untrusted_remote_metadata", "executable": False,
        }],
    })
    calls = []

    async def fake_call(endpoint_id, tool_name, arguments):
        calls.append((endpoint_id, tool_name, arguments))
        return {"content": ["two useful results"]}

    monkeypatch.setattr(api, "call_mcp_read_only_tool", fake_call)
    with TestClient(app) as client:
        endpoint = client.post(
            "/control-plane/endpoints",
            json={"name": "MCP broker test", "protocol": "mcp",
                  "base_url": "https://mcp.example.org/mcp"},
        ).json()
        endpoint_id = endpoint["endpoint_id"]
        client.patch(f"/control-plane/endpoints/{endpoint_id}", json={"enabled": True})
        assert client.post(f"/control-plane/endpoints/{endpoint_id}/discover").status_code == 200
        mapping = client.post(
            "/control-plane/mcp/mappings",
            json={"endpoint_id": endpoint_id, "tool_name": "search_docs",
                  "owner_confirmed_read_only": True},
        ).json()

        payload = {"agent_id": "research-synthesist",
                   "arguments": {"query": "MCP documentation"}}
        denied = client.post(
            f"/control-plane/mcp/mappings/{mapping['mapping_id']}/execute",
            json=payload,
        )
        assert denied.status_code == 403
        assert calls == []

        grant = client.post(
            "/control-plane/capabilities",
            json={"agent_id": "research-synthesist", "capability": "tool.mcp.read"},
        )
        assert grant.status_code == 201
        executed = client.post(
            f"/control-plane/mcp/mappings/{mapping['mapping_id']}/execute",
            json=payload,
        )

    assert executed.status_code == 200
    assert executed.json()["result"]["content"] == ["two useful results"]
    assert calls == [(endpoint_id, "search_docs", {"query": "MCP documentation"})]
