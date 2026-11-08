from fastapi.testclient import TestClient

from ai_os.api import app


def test_mcp_provider_catalog_is_available_and_safe():
    with TestClient(app) as client:
        response = client.get("/integrations/mcp/providers")

    assert response.status_code == 200
    payload = response.json()
    assert payload["discovery"]["official_registry"].startswith("https://")
    assert len(payload["providers"]) >= 40
    assert all(item["configured"] is False for item in payload["providers"])
    assert all(item["execution_enabled"] is False for item in payload["providers"])
    assert all("secret" not in item for item in payload["providers"])
    assert {"github", "google-drive", "slack", "notion", "wordpress", "woocommerce", "stripe"}.issubset(
        {item["id"] for item in payload["providers"]}
    )
