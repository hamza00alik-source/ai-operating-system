import pytest
from fastapi.testclient import TestClient

from ai_os.api import app
from ai_os.db import initialize_database


@pytest.fixture
def session_client(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_API_KEY", "owner-session-test-key")
    monkeypatch.setenv("AI_OS_DATABASE_URL", "sqlite:///" + str(tmp_path / "owner-session.db"))
    monkeypatch.delenv("AI_OS_TRUSTED_ORIGINS", raising=False)
    initialize_database()
    with TestClient(app, base_url="https://testserver") as client:
        login = client.post("/auth/session", json={"api_key": "owner-session-test-key"})
        assert login.status_code == 200
        yield client


def test_owner_session_allows_write_from_trusted_vercel_origin(session_client):
    response = session_client.post(
        "/brain/memories/not-a-real-memory/review",
        headers={
            "Origin": "https://ai-operating-system-one.vercel.app",
            "X-Forwarded-Proto": "https",
        },
        json={"decision": "rejected", "note": "auth regression test"},
    )
    # 404 proves the owner session passed authentication and reached the handler.
    assert response.status_code == 404


def test_owner_session_rejects_untrusted_cross_site_origin(session_client):
    response = session_client.post(
        "/brain/memories/not-a-real-memory/review",
        headers={
            "Origin": "https://attacker.example",
            "X-Forwarded-Proto": "https",
        },
        json={"decision": "rejected", "note": "auth regression test"},
    )
    assert response.status_code == 401


def test_owner_dashboard_mobile_navigation_is_horizontally_scrollable():
    response = TestClient(app).get("/owner")
    assert response.status_code == 200
    html = response.text
    assert "@media(max-width:680px)" in html
    mobile_rules = html.split("@media(max-width:680px)", 1)[1].split("</style>", 1)[0]
    assert "overflow-x:auto" in mobile_rules
    assert "overflow-y:hidden" in mobile_rules
    assert "flex-wrap:nowrap" in mobile_rules
    assert "-webkit-overflow-scrolling:touch" in mobile_rules

def test_owner_dashboard_office_uses_live_twelve_department_data():
    response = TestClient(app).get("/owner")
    assert response.status_code == 200
    html = response.text
    assert 'id="officeDepartmentGrid"' in html
    assert 'id="officeSelected"' in html
    assert '"/company/departments"' in html
    assert '"/tasks"' in html
    assert '"/agent-runs"' in html
    assert "on-demand" in html
    assert "Drag to rotate" in html or "Drag to rotate" in html



def test_owner_dashboard_has_real_wordpress_and_woocommerce_connect_controls():
    response = TestClient(app).get("/owner")
    assert response.status_code == 200
    html = response.text
    assert 'id="integrationSiteUrl"' in html
    assert 'id="integrationUsername"' in html
    assert 'id="integrationConsumerKey"' in html
    assert 'Connect & verify account' in html
    assert '/connect' in html
    assert 'wordpress' in html
    assert 'woocommerce' in html
