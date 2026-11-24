from fastapi.testclient import TestClient

from opencompany_app.api import app


def test_owner_dashboard_exposes_brain_memory_review_workflow():
    with TestClient(app, base_url="https://testserver") as client:
        response = client.get("/owner")

    assert response.status_code == 200
    page = response.text
    assert "OpenCompany Brain · memory review" in page
    assert 'id="brain-memory-form"' in page
    assert 'id="brain-filter"' in page
    assert 'id="brain-list-scope"' in page
    assert 'value="business:physical-agency"' in page
    assert 'value="business:physical-brand"' in page
    assert 'value="business:digital-products"' in page
    assert 'value="company"' in page
    assert 'value="business"' in page
    assert 'value="agent"' in page
    assert "/brain/memories" in page
    assert "params.set(\"scope\",scope)" in page
    assert "/decision" in page
    assert "Agents cannot use it until you approve it." in page
    assert "Approved content may be recalled by agents in its scope." in page
